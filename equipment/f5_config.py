"""Configuration F5 BIG-IP (SSH, chemins UCS, transfert Windows)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from django.conf import settings
from django.utils import timezone as dj_timezone
from zoneinfo import ZoneInfo

from .adapters.base import BackupAdapterError
from .models import BackupJob


def _equipment_extra(job: BackupJob) -> dict:
    extra = job.equipment.extra
    return extra if isinstance(extra, dict) else {}


def credentials_from_job(job: BackupJob) -> tuple[str, str] | None:
    raw = getattr(job, "_backup_credentials", None)
    if not isinstance(raw, dict):
        return None
    user = (raw.get("username") or "").strip()
    password = raw.get("password") or ""
    if user and password:
        return user, password
    return None


def f5_credentials(job: BackupJob) -> tuple[str, str, str]:
    """Identifiants F5 — même couple pour l'API HA (iControl) et le SSH."""
    from_form = credentials_from_job(job)
    if from_form:
        return from_form[0], from_form[1], "form"

    extra = _equipment_extra(job)
    for user_key, pass_key in (
        ("ssh_user", "ssh_password"),
        ("api_user", "api_password"),
        ("icontrol_user", "icontrol_password"),
    ):
        if extra.get(user_key) and extra.get(pass_key):
            return (
                str(extra[user_key]).strip(),
                str(extra[pass_key]),
                "extra",
            )

    from .f5_credentials import env_f5_user_password

    user, password = env_f5_user_password()
    if not user or not password:
        raise BackupAdapterError("Identifiants F5 requis.")
    return user, password, "env"


def api_credentials(job: BackupJob) -> tuple[str, str, str]:
    return f5_credentials(job)


def ssh_credentials(job: BackupJob) -> tuple[str, str, str]:
    return f5_credentials(job)


def integration_mode(job: BackupJob) -> str:
    if credentials_from_job(job):
        return "ssh"
    extra = _equipment_extra(job)
    mode = (extra.get("integration") or extra.get("integration_mode") or "").strip().lower()
    if mode in ("ssh", "icontrol"):
        return "ssh"
    if mode == "demo":
        return "demo"
    env_mode = os.environ.get("F5_INTEGRATION", "").strip().lower()
    if env_mode in ("ssh", "icontrol"):
        return "ssh"
    if extra.get("ssh_user") and extra.get("ssh_password"):
        return "ssh"
    if extra.get("icontrol_user") and extra.get("icontrol_password"):
        return "ssh"
    from .f5_credentials import env_f5_user_password

    user, password = env_f5_user_password()
    if user and password:
        return "ssh"
    return "demo"


def ssh_port() -> int:
    return int(getattr(settings, "F5_SSH_PORT", 22) or 22)


def ssh_save_timeout() -> int:
    return int(getattr(settings, "F5_SSH_SAVE_TIMEOUT", 7200) or 7200)


def ucs_device_dir() -> str:
    raw = getattr(settings, "F5_UCS_DEVICE_DIR", "/var/local/ucs") or "/var/local/ucs"
    return raw.rstrip("/")


def backup_root() -> Path:
    root = getattr(settings, "F5_BACKUP_ROOT", None)
    if root is None:
        root = Path(settings.BASE_DIR) / "backups" / "f5"
    return Path(root)


def backup_folder_date() -> str:
    """Dossier date Windows : YYYY-MM-DD."""
    tz = ZoneInfo(settings.TIME_ZONE)
    return dj_timezone.localtime(dj_timezone.now(), timezone=tz).strftime("%Y-%m-%d")


def ucs_filename(short_hostname: str) -> str:
    """Ex. f5-dc01-ltm-20260610-174500.ucs"""
    tz = ZoneInfo(settings.TIME_ZONE)
    stamp = dj_timezone.localtime(dj_timezone.now(), timezone=tz).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", short_hostname.strip().lower())
    safe = re.sub(r"-+", "-", safe).strip("-")[:40] or "host"
    return f"f5-{safe}-{stamp}.ucs"


def normalize_mgmt_host(address: str) -> str:
    addr = address.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if addr.lower().startswith(prefix):
            addr = addr[len(prefix) :]
    if "/" in addr:
        addr = addr.split("/", 1)[0]
    if not addr:
        raise BackupAdapterError("Adresse F5 invalide.")
    return addr


def windows_scp_config() -> dict | None:
    host = (
        os.environ.get("F5_WINDOWS_SCP_HOST", "").strip()
        or getattr(settings, "F5_WINDOWS_SCP_HOST", "")
        or os.environ.get("F5_SCP_HOST", "").strip()
        or getattr(settings, "F5_SCP_HOST", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_HOST", "")
    )
    username = (
        os.environ.get("F5_WINDOWS_SCP_USERNAME", "").strip()
        or getattr(settings, "F5_WINDOWS_SCP_USERNAME", "")
        or os.environ.get("F5_SCP_USERNAME", "").strip()
        or getattr(settings, "F5_SCP_USERNAME", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_USERNAME", "")
    )
    password = (
        getattr(settings, "F5_WINDOWS_SCP_PASSWORD", "")
        or getattr(settings, "F5_SCP_PASSWORD", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_PASSWORD", "")
    )
    if not host or not username or not password:
        return None
    port = (
        os.environ.get("F5_WINDOWS_SCP_PORT", "").strip()
        or getattr(settings, "F5_WINDOWS_SCP_PORT", None)
        or os.environ.get("F5_SCP_PORT", "").strip()
        or getattr(settings, "F5_SCP_PORT", None)
        or getattr(settings, "NITROKEY_WINDOWS_SCP_PORT", 22)
    )
    remote_parent = (
        os.environ.get("F5_WINDOWS_SCP_REMOTE_DIR", "").strip()
        or getattr(settings, "F5_WINDOWS_SCP_REMOTE_DIR", "")
        or os.environ.get("F5_SCP_REMOTE_PARENT_DIR", "").strip()
        or getattr(settings, "F5_SCP_REMOTE_PARENT_DIR", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_REMOTE_DIR", "")
    )
    return {
        "host": host,
        "port": int(port) if port else 22,
        "username": username,
        "password": password,
        "remote_parent": remote_parent.replace("\\", "/").rstrip("/"),
    }


def windows_remote_path(config: dict, folder_date: str, filename: str) -> str:
    """
    Chemin SCP Windows : {F5_WINDOWS_SCP_REMOTE_DIR}/{date}/{fichier}.ucs
    Ex. E:/NetConfig_Backup/DC01/F5/2026-06-10/f5-dc01-ltm-20260610-174500.ucs
    """
    import posixpath

    parent = config["remote_parent"]
    if parent:
        return posixpath.join(parent, folder_date, filename)
    return posixpath.join(folder_date, filename)
