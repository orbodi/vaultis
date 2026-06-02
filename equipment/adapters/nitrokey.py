"""
Adaptateur Nitrokey / NetHSM.

Appel API (équivalent) ::

  curl -k -X POST 'https://{host}/api/v1/system/backup' \\
    -u '{user}:{password}' \\
    -H 'Accept: application/octet-stream' \\
    --output backup.bkp

`-k` → NITROKEY_NETHSM_VERIFY_TLS=false ou extra {"verify_tls": false}.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import shutil
import ssl
import socket
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone as dj_timezone

from .base import BackupAdapterError
from .messages import backup_success_message

if TYPE_CHECKING:
    from equipment.models import BackupJob

logger = logging.getLogger(__name__)


def _equipment_extra(job: BackupJob) -> dict:
    extra = job.equipment.extra
    return extra if isinstance(extra, dict) else {}


def _integration_mode(job: BackupJob) -> str:
    if _credentials_from_job(job):
        return "nethsm"
    extra = _equipment_extra(job)
    mode = (extra.get("integration") or extra.get("integration_mode") or "").strip().lower()
    if mode in ("nethsm", "demo"):
        return mode
    if os.environ.get("NITROKEY_INTEGRATION", "").strip().lower() == "nethsm":
        return "nethsm"
    return "demo"


def _credentials_from_job(job: BackupJob) -> tuple[str, str] | None:
    raw = getattr(job, "_backup_credentials", None)
    if not isinstance(raw, dict):
        return None
    user = (raw.get("username") or "").strip()
    password = raw.get("password") or ""
    if user and password:
        return user, password
    return None


def _nethsm_credentials(job: BackupJob) -> tuple[str, str]:
    from_form = _credentials_from_job(job)
    if from_form:
        return from_form

    extra = _equipment_extra(job)
    user = (extra.get("nethsm_user") or os.environ.get("NITROKEY_NETHSM_USER") or "").strip()
    password = (
        extra.get("nethsm_password") or os.environ.get("NITROKEY_NETHSM_PASSWORD") or ""
    ).strip()
    if not user or not password:
        raise BackupAdapterError("Identifiants API requis.")
    return user, password


def _verify_tls(job: BackupJob) -> bool:
    extra = _equipment_extra(job)
    if "verify_tls" in extra:
        return bool(extra["verify_tls"])
    return getattr(settings, "NITROKEY_NETHSM_VERIFY_TLS", True)


def _api_base(host_address: str) -> str:
    addr = host_address.strip().rstrip("/")
    if not addr:
        raise BackupAdapterError("Adresse NetHSM invalide.")
    if addr.startswith(("http://", "https://")):
        root = addr
    else:
        root = f"https://{addr}"
    if "/api/" in root:
        return root.rstrip("/")
    return f"{root}/api/v1"


def _backup_root() -> Path:
    root = getattr(settings, "NITROKEY_BACKUP_ROOT", None)
    if root is None:
        root = Path(settings.BASE_DIR) / "backups" / "nitrokey"
    return Path(root)


def _backup_filename(host_address: str) -> str:
    """Nom horodaté (fuseau Django) pour tri chronologique."""
    stamp = dj_timezone.localtime().strftime("%Y-%m-%d_%H-%M-%S")
    safe_host = (
        host_address.replace("://", "_")
        .replace(":", "_")
        .replace("/", "_")
        .replace(".", "_")[:60]
    )
    return f"{stamp}_nethsm_{safe_host}.bkp"


def _windows_transfer_root() -> Path | None:
    root = getattr(settings, "NITROKEY_WINDOWS_TRANSFER_DIR", None)
    if not root:
        return None
    return Path(root)


def _transfer_mode() -> str:
    mode = (getattr(settings, "NITROKEY_TRANSFER_MODE", "auto") or "auto").strip().lower()
    if mode in {"auto", "none", "dir", "smb", "scp"}:
        return mode
    raise BackupAdapterError("NITROKEY_TRANSFER_MODE invalide (auto|none|dir|smb|scp).")


def _windows_smb_config() -> dict | None:
    host = getattr(settings, "NITROKEY_WINDOWS_SMB_HOST", "")
    share = getattr(settings, "NITROKEY_WINDOWS_SMB_SHARE", "")
    if not host or not share:
        return None
    username = getattr(settings, "NITROKEY_WINDOWS_SMB_USERNAME", "")
    password = getattr(settings, "NITROKEY_WINDOWS_SMB_PASSWORD", "")
    if not username or not password:
        raise BackupAdapterError("Identifiants SMB Windows requis (username/password).")
    return {
        "host": host,
        "share": share,
        "remote_dir": getattr(settings, "NITROKEY_WINDOWS_SMB_REMOTE_DIR", "").strip("/"),
        "username": username,
        "password": password,
        "domain": getattr(settings, "NITROKEY_WINDOWS_SMB_DOMAIN", ""),
        "port": getattr(settings, "NITROKEY_WINDOWS_SMB_PORT", 445),
    }


def _windows_scp_config() -> dict | None:
    host = getattr(settings, "NITROKEY_WINDOWS_SCP_HOST", "")
    username = getattr(settings, "NITROKEY_WINDOWS_SCP_USERNAME", "")
    if not host or not username:
        return None
    password = getattr(settings, "NITROKEY_WINDOWS_SCP_PASSWORD", "")
    if not password:
        raise BackupAdapterError("Mot de passe SCP Windows requis.")
    return {
        "host": host,
        "port": getattr(settings, "NITROKEY_WINDOWS_SCP_PORT", 22),
        "username": username,
        "password": password,
        "remote_dir": getattr(settings, "NITROKEY_WINDOWS_SCP_REMOTE_DIR", "").strip(),
    }


def _transfer_to_windows_smb(config: dict, filename: str, payload: bytes) -> None:
    from smb.SMBConnection import SMBConnection

    client_name = socket.gethostname()[:15] or "vaultis"
    conn = SMBConnection(
        config["username"],
        config["password"],
        client_name,
        config["host"],
        domain=config["domain"] or "",
        use_ntlm_v2=True,
        is_direct_tcp=True,
    )
    if not conn.connect(config["host"], int(config["port"]), timeout=30):
        raise BackupAdapterError("Connexion SMB Windows échouée.")
    try:
        remote_dir = config["remote_dir"]
        remote_path = f"{remote_dir}/{filename}" if remote_dir else filename
        conn.storeFile(config["share"], remote_path, io.BytesIO(payload))
    finally:
        conn.close()


def _transfer_to_windows_scp(config: dict, filename: str, payload: bytes) -> None:
    import posixpath

    import paramiko

    remote_dir = config["remote_dir"].replace("\\", "/").rstrip("/")
    remote_path = posixpath.join(remote_dir, filename) if remote_dir else filename
    transport = paramiko.Transport((config["host"], int(config["port"])))
    transport.connect(username=config["username"], password=config["password"])
    try:
        sftp = paramiko.SFTPClient.from_transport(transport)
        with sftp.file(remote_path, "wb") as remote_file:
            remote_file.write(payload)
    finally:
        transport.close()


def _fetch_nethsm_backup(host_address: str, user: str, password: str, *, verify_tls: bool) -> bytes:
    url = f"{_api_base(host_address)}/system/backup"
    token = base64.b64encode(f"{user}:{password}".encode("latin-1")).decode("ascii")
    request = Request(
        url,
        method="POST",
        data=b"",
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/octet-stream",
        },
    )
    context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
    try:
        with urlopen(request, timeout=120, context=context) as response:
            return response.read()
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except OSError:
            pass
        detail = f" — {body[:120]}" if body else ""
        raise BackupAdapterError(f"NetHSM HTTP {exc.code}{detail}") from exc
    except URLError as exc:
        raise BackupAdapterError("NetHSM injoignable.") from exc


class Adapter:
    def run_backup(self, job: BackupJob) -> str:
        if not job.equipment_host_id:
            raise BackupAdapterError("Host cible manquant.")
        host = job.equipment_host
        mode = _integration_mode(job)
        if mode == "nethsm":
            return self._run_nethsm(job, host.address)
        return self._run_demo(host.label, host.address)

    def _run_demo(self, label: str, address: str) -> str:
        target = address
        if label.strip():
            target = f"{label.strip()} ({address})"
        return backup_success_message(target)

    def _run_nethsm(self, job: BackupJob, host_address: str) -> str:
        user, password = _nethsm_credentials(job)
        payload = _fetch_nethsm_backup(
            host_address,
            user,
            password,
            verify_tls=_verify_tls(job),
        )
        if not payload:
            raise BackupAdapterError("Backup NetHSM vide.")

        root = _backup_root()
        root.mkdir(parents=True, exist_ok=True)
        filename = _backup_filename(host_address)
        path = root / filename
        path.write_bytes(payload)
        transfer_root = _windows_transfer_root()
        smb_config = _windows_smb_config()
        scp_config = _windows_scp_config()
        mode = _transfer_mode()
        transferred = False

        selected_mode = mode
        if mode == "auto":
            if smb_config is not None:
                selected_mode = "smb"
            elif scp_config is not None:
                selected_mode = "scp"
            elif transfer_root is not None:
                selected_mode = "dir"
            else:
                selected_mode = "none"

        if selected_mode == "smb":
            if smb_config is None:
                raise BackupAdapterError("Configuration SMB incomplète.")
            try:
                _transfer_to_windows_smb(smb_config, filename, payload)
                transferred = True
                logger.info(
                    "Backup copied to Windows SMB host=%s share=%s remote_dir=%s filename=%s",
                    smb_config["host"],
                    smb_config["share"],
                    smb_config["remote_dir"],
                    filename,
                )
            except Exception as exc:
                raise BackupAdapterError(
                    "Backup local ok, transfert SMB Windows impossible. Voir les logs."
                ) from exc
        elif selected_mode == "scp":
            if scp_config is None:
                raise BackupAdapterError("Configuration SCP incomplète.")
            try:
                _transfer_to_windows_scp(scp_config, filename, payload)
                transferred = True
                logger.info(
                    "Backup copied via SCP host=%s port=%s remote_dir=%s filename=%s",
                    scp_config["host"],
                    scp_config["port"],
                    scp_config["remote_dir"],
                    filename,
                )
            except Exception as exc:
                raise BackupAdapterError(
                    "Backup local ok, transfert SCP Windows impossible. Voir les logs."
                ) from exc
        elif selected_mode == "dir":
            if transfer_root is None:
                raise BackupAdapterError("NITROKEY_WINDOWS_TRANSFER_DIR manquant.")
            try:
                transfer_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, transfer_root / filename)
                transferred = True
                logger.info("Backup copied to Windows dir source=%s destination=%s", path, transfer_root)
            except OSError as exc:
                raise BackupAdapterError(
                    "Backup local ok, transfert Windows impossible. Voir les logs."
                ) from exc
        elif selected_mode != "none":
            raise BackupAdapterError("Mode de transfert non pris en charge.")
        size_kb = max(1, len(payload) // 1024)
        if transferred:
            return f"Backup enregistré et transféré — {path.name} ({size_kb} Ko)."
        return f"Backup enregistré — {path.name} ({size_kb} Ko)."
