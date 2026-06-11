"""Logique SSH commune — sauvegarde UCS F5 (HA et standalone)."""

from __future__ import annotations

import logging
import posixpath
from pathlib import Path
from typing import TYPE_CHECKING

from equipment.f5_config import normalize_mgmt_host
from equipment.f5_credentials import f5_credentials
from equipment.f5_variant import (
    F5Variant,
    backup_folder_date,
    backup_root,
    ssh_port,
    ssh_save_timeout,
    ucs_device_dir,
    ucs_filename,
    windows_remote_path,
    windows_scp_config,
)

from .base import BackupAdapterError

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


def _exec_tmsh(client, command: str, *, timeout: int, log_label: str) -> str:
    logger.info("%s tmsh: %s", log_label, command)
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


class F5SSHSession:
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        *,
        port: int,
        log_label: str,
    ) -> None:
        import paramiko

        self.host = host
        self._log_label = log_label
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
            raise BackupAdapterError(
                f"Connexion SSH {log_label} impossible ({host})."
            ) from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> F5SSHSession:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @property
    def client(self):
        return self._client

    def run_backup(
        self,
        *,
        variant: F5Variant,
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
        device_dir = ucs_device_dir(variant)
        remote_ucs = f"{device_dir}/{ucs_name}"
        local_path = local_dir / ucs_name
        save_timeout = ssh_save_timeout(variant)

        _exec_tmsh(
            self._client,
            f"tmsh save sys ucs {ucs_name}",
            timeout=save_timeout,
            log_label=variant.label,
        )
        logger.info("%s UCS généré sur l'équipement : %s", variant.label, remote_ucs)

        try:
            size = _download_ucs_sftp(self._client, remote_ucs, local_path)
            logger.info(
                "%s UCS téléchargé local=%s (%s octets)",
                variant.label,
                local_path,
                size,
            )
        except Exception as exc:
            raise BackupAdapterError(
                f"Téléchargement UCS échoué ({remote_ucs})."
            ) from exc

        try:
            _exec_tmsh(
                self._client,
                f"tmsh delete sys ucs {ucs_name}",
                timeout=120,
                log_label=variant.label,
            )
            logger.info("%s UCS supprimé sur l'équipement : %s", variant.label, ucs_name)
        except BackupAdapterError as exc:
            logger.warning(
                "%s suppression UCS échouée (fichier local conservé) : %s",
                variant.label,
                exc,
            )

        return local_path, ucs_name


def run_f5_ssh_backup(
    job: BackupJob,
    variant: F5Variant,
    mgmt_ip: str,
    host_label: str,
) -> str:
    user, password, cred_source = f5_credentials(job)
    mgmt_host = normalize_mgmt_host(mgmt_ip)
    root = backup_root(variant)
    root.mkdir(parents=True, exist_ok=True)

    logger.info(
        "%s backup SSH start target=%s user=%s cred_source=%s port=%s job_id=%s",
        variant.label,
        mgmt_host,
        user,
        cred_source,
        ssh_port(variant),
        job.pk,
    )

    with F5SSHSession(
        mgmt_host,
        user,
        password,
        port=ssh_port(variant),
        log_label=variant.label,
    ) as session:
        local_path, ucs_name = session.run_backup(
            variant=variant,
            host_label=host_label,
            host_address=mgmt_host,
            local_dir=root,
        )

    win_scp = windows_scp_config(variant)
    transferred = False
    remote_win = ""
    if win_scp is None:
        logger.info(
            "%s transfert SCP Windows ignoré (F5_%s_WINDOWS_SCP_* ou repli "
            "F5_WINDOWS_SCP_* / NITROKEY_WINDOWS_SCP_* non configuré).",
            variant.label,
            variant.env_prefix or "HA",
        )
    if win_scp is not None:
        remote_win = windows_remote_path(win_scp, backup_folder_date(), ucs_name)
        try:
            _upload_to_windows(win_scp, remote_win, local_path)
            transferred = True
            logger.info("%s UCS transféré Windows : %s", variant.label, remote_win)
        except Exception as exc:
            raise BackupAdapterError(
                "Backup local ok, transfert SCP Windows impossible. Voir les logs."
            ) from exc

    size_kb = max(1, local_path.stat().st_size // 1024)
    if transferred:
        return (
            f"UCS {variant.label} enregistré et transféré — {ucs_name} ({size_kb} Ko) "
            f"→ {remote_win}."
        )
    return f"UCS {variant.label} enregistré — {ucs_name} ({size_kb} Ko)."
