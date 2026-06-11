"""Configuration F5 BIG-IP — façade rétrocompatible (variante HA par défaut)."""

from __future__ import annotations

from pathlib import Path

from .f5_credentials import (
    credentials_from_job,
    f5_credentials,
)
from .f5_variant import F5 as _F5_VARIANT
from .f5_variant import (
    backup_folder_date,
    backup_root as _backup_root,
    integration_mode as _integration_mode,
    ssh_port as _ssh_port,
    ssh_save_timeout as _ssh_save_timeout,
    ucs_device_dir as _ucs_device_dir,
    ucs_filename,
    windows_remote_path,
    windows_scp_config as _windows_scp_config,
)
from .adapters.base import BackupAdapterError
from .models import BackupJob


def api_credentials(job: BackupJob) -> tuple[str, str, str]:
    return f5_credentials(job)


def ssh_credentials(job: BackupJob) -> tuple[str, str, str]:
    return f5_credentials(job)


def integration_mode(job: BackupJob) -> str:
    return _integration_mode(job, _F5_VARIANT)


def ssh_port() -> int:
    return _ssh_port(_F5_VARIANT)


def ssh_save_timeout() -> int:
    return _ssh_save_timeout(_F5_VARIANT)


def ucs_device_dir() -> str:
    return _ucs_device_dir(_F5_VARIANT)


def backup_root() -> Path:
    return _backup_root(_F5_VARIANT)


def windows_scp_config() -> dict | None:
    return _windows_scp_config(_F5_VARIANT)


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
