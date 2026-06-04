"""Configuration Arbor AED (dossiers source / distant par DC, SCP)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from django.conf import settings

from .adapters.base import BackupAdapterError

ARBOR_DC_KEYS = ("DC01", "DC02")


def normalize_dc_key(value: str) -> str | None:
    """Normalise DC01 / DC02."""
    if not value or not str(value).strip():
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", str(value).strip()).upper()
    aliases = {
        "DC01": "DC01",
        "DC1": "DC01",
        "DC02": "DC02",
        "DC2": "DC02",
    }
    if compact in aliases:
        return aliases[compact]
    if compact.startswith("DC01"):
        return "DC01"
    if compact.startswith("DC02"):
        return "DC02"
    return None


def arbor_active_dcs() -> list[str]:
    """
    DC à traiter pour ce job (ARBOR_AED_ACTIVE_DCS=DC01,DC02).
    Les DC non listés sont ignorés.
    """
    raw = os.environ.get("ARBOR_AED_ACTIVE_DCS", "").strip()
    if not raw:
        raw = getattr(settings, "ARBOR_AED_ACTIVE_DCS", "") or ""
    if not raw:
        raise BackupAdapterError(
            "Aucun DC Arbor AED actif. Définir ARBOR_AED_ACTIVE_DCS (ex. DC01,DC02)."
        )

    active: list[str] = []
    unknown: list[str] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        dc = normalize_dc_key(token)
        if dc is None:
            unknown.append(token)
            continue
        if dc not in active:
            active.append(dc)

    if unknown:
        raise BackupAdapterError(
            f"DC Arbor AED invalide dans ARBOR_AED_ACTIVE_DCS : {', '.join(unknown)}."
        )
    if not active:
        raise BackupAdapterError(
            "ARBOR_AED_ACTIVE_DCS est vide ou invalide (ex. DC01,DC02)."
        )
    return active


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if raw:
        return Path(raw)
    return None


def arbor_source_dirs() -> dict[str, Path]:
    """Dossiers incoming par DC (ARBOR_AED_SOURCE_DIR_DC01 / _DC02)."""
    mapping: dict[str, Path] = {}
    for dc in ARBOR_DC_KEYS:
        path = _env_path(f"ARBOR_AED_SOURCE_DIR_{dc}")
        if path is None:
            configured = getattr(settings, "ARBOR_AED_SOURCE_DIRS", None) or {}
            path = configured.get(dc)
        if path is not None:
            mapping[dc] = Path(path)

    legacy = getattr(settings, "ARBOR_AED_SOURCE_DIR", None)
    if legacy:
        legacy_path = Path(legacy)
        for dc in ARBOR_DC_KEYS:
            mapping.setdefault(dc, legacy_path)

    return mapping


def arbor_source_dir_for_dc(dc: str) -> Path:
    dirs = arbor_source_dirs()
    if dc not in dirs:
        raise BackupAdapterError(
            f"Dossier source non configuré pour {dc} (ARBOR_AED_SOURCE_DIR_{dc})."
        )
    path = dirs[dc]
    if not path.is_dir():
        raise BackupAdapterError(f"Dossier source Arbor AED introuvable pour {dc} : {path}")
    return path


def arbor_staging_root(job_id: int) -> Path:
    root = getattr(settings, "ARBOR_AED_STAGING_DIR", None)
    if root is None:
        root = Path(settings.BASE_DIR) / "backups" / "arbor_aed" / "staging"
    return Path(root) / f"job-{job_id}"


def arbor_staging_for_dc(job_id: int, dc: str) -> Path:
    return arbor_staging_root(job_id) / dc


def arbor_remote_parent_for_dc(dc: str) -> str:
    """Dossier mère distant obligatoire par DC : ARBOR_AED_REMOTE_PARENT_DIR_DC01 / _DC02."""
    raw = os.environ.get(f"ARBOR_AED_REMOTE_PARENT_DIR_{dc}", "").strip()
    if not raw:
        per_dc = getattr(settings, "ARBOR_AED_REMOTE_PARENT_DIRS", None) or {}
        raw = (per_dc.get(dc) or "").strip()
    if not raw:
        raise BackupAdapterError(
            f"Dossier mère distant non configuré pour {dc}. "
            f"Définir ARBOR_AED_REMOTE_PARENT_DIR_{dc} dans .env."
        )
    return raw.replace("\\", "/").rstrip("/")


def arbor_move_source_files() -> bool:
    return getattr(settings, "ARBOR_AED_MOVE_SOURCE", False)


def scp_config_from_settings() -> dict:
    """SCP : variables ARBOR_AED_SCP_* ou repli sur NITROKEY_WINDOWS_SCP_*."""
    host = (
        os.environ.get("ARBOR_AED_SCP_HOST", "").strip()
        or getattr(settings, "ARBOR_AED_SCP_HOST", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_HOST", "")
    )
    raw_port = (
        os.environ.get("ARBOR_AED_SCP_PORT", "").strip()
        or getattr(settings, "ARBOR_AED_SCP_PORT", None)
        or getattr(settings, "NITROKEY_WINDOWS_SCP_PORT", 22)
    )
    port = int(raw_port) if raw_port else 22
    username = (
        os.environ.get("ARBOR_AED_SCP_USERNAME", "").strip()
        or getattr(settings, "ARBOR_AED_SCP_USERNAME", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_USERNAME", "")
    )
    password = (
        getattr(settings, "ARBOR_AED_SCP_PASSWORD", "")
        or getattr(settings, "NITROKEY_WINDOWS_SCP_PASSWORD", "")
    )
    if not host or not username or not password:
        raise BackupAdapterError("Configuration SCP incomplète pour Arbor AED.")
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }
