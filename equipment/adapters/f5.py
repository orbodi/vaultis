"""
Adaptateur F5 BIG-IP — sauvegarde UCS via SSH.

1. Connexion SSH au host de management
2. tmsh save sys ucs <nom> (attente fin de génération)
3. SFTP : /var/local/ucs/<nom>.ucs → F5_BACKUP_ROOT
4. tmsh delete sys ucs <nom>
5. SCP optionnel vers Windows
"""

from __future__ import annotations

import logging
import posixpath
from pathlib import Path
from typing import TYPE_CHECKING

from equipment.f5_config import (
    backup_folder_date,
    backup_root,
    f5_credentials,
    integration_mode,
    normalize_mgmt_host,
    ssh_port,
    ssh_save_timeout,
    ucs_device_dir,
    ucs_filename,
    windows_remote_path,
    windows_scp_config,
)
from equipment.f5_ha import ha_peer_addresses, resolve_active_mgmt_ip_for_job

from .base import BackupAdapterError
from .messages import backup_success_message

if TYPE_CHECKING:
    from equipment.models import BackupJob

logger = logging.getLogger(__name__)


def _short_hostname_from_label(label: str, address: str) -> str:
    if label.strip():
        token = label.strip().split()[0].lower()
        return token.replace(".", "-")[:40]
    host = normalize_mgmt_host(address)
    return host.split(".")[0].lower()[:40]


def _read_short_hostname_ssh(client, *, label: str, address: str) -> str:
    fallback = _short_hostname_from_label(label, address)
    try:
        _, stdout, _ = client.exec_command(
            "tmsh -q list sys global hostname one-field hostname",
            timeout=30,
        )
        raw = stdout.read().decode("utf-8", errors="replace").strip()
        if raw:
            return raw.split(".")[0].lower()[:40]
    except Exception as exc:
        logger.warning("F5 hostname query failed, fallback label/address: %s", exc)
    return fallback


def _exec_tmsh(client, command: str, *, timeout: int) -> str:
    logger.info("F5 tmsh: %s", command)
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if exit_code != 0:
        detail = err or out or f"code {exit_code}"
        raise BackupAdapterError(f"Commande F5 échouée : {command} — {detail[:300]}")
    return out


def _download_ucs_sftp(client, remote_path: str, local_path: Path) -> int:
    sftp = client.open_sftp()
    try:
        sftp.get(remote_path, str(local_path))
    finally:
        sftp.close()
    size = local_path.stat().st_size
    if size <= 0:
        raise BackupAdapterError(f"Fichier UCS vide après téléchargement : {remote_path}")
    return size


def _upload_to_windows(config: dict, remote_path: str, local_path: Path) -> None:
    import paramiko

    from equipment.scp_transfer import _ensure_remote_dir

    transport = paramiko.Transport((config["host"], int(config["port"])))
    transport.connect(username=config["username"], password=config["password"])
    try:
        sftp = paramiko.SFTPClient.from_transport(transport)
        remote_dir = posixpath.dirname(remote_path)
        if remote_dir:
            _ensure_remote_dir(sftp, remote_dir)
        with local_path.open("rb") as src:
            with sftp.file(remote_path, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
    finally:
        transport.close()


class _F5SSHSession:
    def __init__(self, host: str, user: str, password: str, *, port: int) -> None:
        import paramiko

        self.host = host
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._client.connect(
                host,
                port=port,
                username=user,
                password=password,
                timeout=60,
                allow_agent=False,
                look_for_keys=False,
            )
        except Exception as exc:
            raise BackupAdapterError(f"Connexion SSH F5 impossible ({host}).") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> _F5SSHSession:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @property
    def client(self):
        return self._client

    def run_backup(
        self,
        *,
        host_label: str,
        host_address: str,
        local_dir: Path,
    ) -> tuple[Path, str]:
        short_name = _read_short_hostname_ssh(
            self._client,
            label=host_label,
            address=host_address,
        )
        ucs_name = ucs_filename(short_name)
        device_dir = ucs_device_dir()
        remote_ucs = f"{device_dir}/{ucs_name}"
        local_path = local_dir / ucs_name
        save_timeout = ssh_save_timeout()

        _exec_tmsh(
            self._client,
            f"tmsh save sys ucs {ucs_name}",
            timeout=save_timeout,
        )
        logger.info("F5 UCS généré sur l'équipement : %s", remote_ucs)

        try:
            size = _download_ucs_sftp(self._client, remote_ucs, local_path)
            logger.info("F5 UCS téléchargé local=%s (%s octets)", local_path, size)
        except Exception as exc:
            raise BackupAdapterError(
                f"Téléchargement UCS échoué ({remote_ucs})."
            ) from exc

        try:
            _exec_tmsh(self._client, f"tmsh delete sys ucs {ucs_name}", timeout=120)
            logger.info("F5 UCS supprimé sur l'équipement : %s", ucs_name)
        except BackupAdapterError as exc:
            logger.warning("F5 suppression UCS échouée (fichier local conservé) : %s", exc)

        return local_path, ucs_name


def _attach_resolved_host(job: BackupJob, active_ip: str) -> str:
    """Associe le job au host admin correspondant, retourne un libellé pour les logs."""
    for host in job.equipment.hosts.order_by("sort_order", "pk"):
        if normalize_mgmt_host(host.address) == active_ip:
            job.equipment_host = host
            job.save(update_fields=["equipment_host"])
            return host.label.strip() or active_ip
    return active_ip


class Adapter:
    def run_backup(self, job: BackupJob) -> str:
        mode = integration_mode(job)
        if mode == "ssh":
            return self._run_ssh(job)
        peers = ha_peer_addresses(job)
        return self._run_demo("", peers[0])

    def _run_demo(self, label: str, address: str) -> str:
        target = address
        if label.strip():
            target = f"{label.strip()} ({address})"
        return backup_success_message(target)

    def _run_ssh(self, job: BackupJob) -> str:
        user, password, cred_source = f5_credentials(job)
        active_ip = resolve_active_mgmt_ip_for_job(job, user, password)
        host_label = _attach_resolved_host(job, active_ip)
        root = backup_root()
        root.mkdir(parents=True, exist_ok=True)

        logger.info(
            "F5 backup SSH start active=%s user=%s cred_source=%s port=%s",
            active_ip,
            user,
            cred_source,
            ssh_port(),
        )

        with _F5SSHSession(active_ip, user, password, port=ssh_port()) as session:
            local_path, ucs_name = session.run_backup(
                host_label=host_label,
                host_address=active_ip,
                local_dir=root,
            )

        win_scp = windows_scp_config()
        transferred = False
        remote_win = ""
        if win_scp is not None:
            remote_win = windows_remote_path(win_scp, backup_folder_date(), ucs_name)
            try:
                _upload_to_windows(win_scp, remote_win, local_path)
                transferred = True
                logger.info("F5 UCS transféré Windows : %s", remote_win)
            except Exception as exc:
                raise BackupAdapterError(
                    "Backup local ok, transfert SCP Windows impossible. Voir les logs."
                ) from exc

        size_kb = max(1, local_path.stat().st_size // 1024)
        if transferred:
            return (
                f"UCS F5 enregistré et transféré — {ucs_name} ({size_kb} Ko) "
                f"→ {remote_win}."
            )
        return f"UCS F5 enregistré — {ucs_name} ({size_kb} Ko)."
