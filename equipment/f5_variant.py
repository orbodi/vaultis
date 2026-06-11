"""Variantes F5 (HA cluster, DN standalone) — chemins et intégration par type."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone as dj_timezone
from zoneinfo import ZoneInfo

from .adapters.base import BackupAdapterError
from .models import BackupJob

F5_FAMILY_SLUGS = frozenset({"f5", "f5-dn1", "f5-dn2"})


@dataclass(frozen=True)
class F5Variant:
    slug: str
    env_prefix: str
    label: str
    ha: bool


F5 = F5Variant(slug="f5", env_prefix="", label="F5", ha=True)
F5_DN1 = F5Variant(slug="f5-dn1", env_prefix="F5_DN1", label="F5-DN1", ha=False)
F5_DN2 = F5Variant(slug="f5-dn2", env_prefix="F5_DN2", label="F5-DN2", ha=False)

BY_SLUG: dict[str, F5Variant] = {
    F5.slug: F5,
    F5_DN1.slug: F5_DN1,
    F5_DN2.slug: F5_DN2,
}


def is_f5_family_slug(slug: str) -> bool:
    return slug in F5_FAMILY_SLUGS


def is_f5_ha_slug(slug: str) -> bool:
    return slug == "f5"


def is_f5_standalone_slug(slug: str) -> bool:
    return slug in ("f5-dn1", "f5-dn2")


def is_f5_standalone_adapter(adapter_key: str) -> bool:
    return ".f5_dn" in (adapter_key or "")


def is_f5_standalone_equipment(slug: str, adapter_key: str) -> bool:
    return is_f5_standalone_slug(slug) or is_f5_standalone_adapter(adapter_key)


def is_f5_ha_equipment(slug: str, adapter_key: str) -> bool:
    return slug == "f5" and not is_f5_standalone_equipment(slug, adapter_key)


def variant_for_slug(slug: str) -> F5Variant:
    try:
        return BY_SLUG[slug]
    except KeyError as exc:
        raise BackupAdapterError(f"Type F5 non pris en charge : {slug}.") from exc


def variant_for_job(job: BackupJob) -> F5Variant:
    return variant_for_slug(job.equipment.equipment_type.slug)


def _env_or_setting(*keys: str, default: str = "") -> str:
    for key in keys:
        if not key:
            continue
        raw = os.environ.get(key, "").strip()
        if raw:
            return raw
        val = getattr(settings, key, "")
        if isinstance(val, Path):
            return str(val)
        if val not in (None, ""):
            return str(val).strip() if isinstance(val, str) else str(val)
    return default


def _shared_f5_keys(suffix: str) -> tuple[str, ...]:
    """Intégration, SSH, identifiants — communs à HA et DN."""
    return (f"F5_{suffix}",)


def _variant_path_keys(variant: F5Variant, suffix: str) -> tuple[str, ...]:
    """Chemins de stockage — spécifiques DN1/DN2 avec repli F5_*."""
    keys: list[str] = []
    if variant.env_prefix:
        keys.append(f"{variant.env_prefix}_{suffix}")
    keys.append(f"F5_{suffix}")
    return tuple(keys)


def integration_mode(job: BackupJob, variant: F5Variant) -> str:
    from .f5_credentials import credentials_from_job

    if credentials_from_job(job):
        return "ssh"
    extra = job.equipment.extra if isinstance(job.equipment.extra, dict) else {}
    mode = (extra.get("integration") or extra.get("integration_mode") or "").strip().lower()
    if mode in ("ssh", "icontrol"):
        return "ssh"
    env_mode = _env_or_setting(*_shared_f5_keys("INTEGRATION")).lower()
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
    if mode == "demo":
        return "demo"
    return "demo"


def raise_unless_demo_allowed() -> None:
    """Bloque le faux succès démo en production (DEBUG=False)."""
    from django.conf import settings

    if settings.DEBUG:
        return
    raise BackupAdapterError(
        "Sauvegarde F5 impossible : intégration SSH non configurée. "
        "Définissez F5_INTEGRATION=ssh et F5_SSH_USER / F5_SSH_PASSWORD "
        "(ou F5_SSH_USER_FILE / F5_SSH_PASSWORD_FILE sous /app/secrets) "
        "dans .env, puis redémarrez les conteneurs web et scheduler."
    )


def ssh_port(variant: F5Variant) -> int:
    raw = _env_or_setting(*_shared_f5_keys("SSH_PORT"), default="22")
    return int(raw or 22)


def ssh_save_timeout(variant: F5Variant) -> int:
    raw = _env_or_setting(*_shared_f5_keys("SSH_SAVE_TIMEOUT"), default="7200")
    return int(raw or 7200)


def ucs_device_dir(variant: F5Variant) -> str:
    raw = _env_or_setting(
        *_shared_f5_keys("UCS_DEVICE_DIR"),
        default="/var/local/ucs",
    )
    return (raw or "/var/local/ucs").rstrip("/")


def backup_root(variant: F5Variant) -> Path:
    for key in _variant_path_keys(variant, "BACKUP_ROOT"):
        raw = _env_or_setting(key)
        if raw:
            return Path(raw)
    sub = variant.slug.replace("-", "_")
    return Path(settings.BASE_DIR) / "backups" / sub


def backup_folder_date() -> str:
    tz = ZoneInfo(settings.TIME_ZONE)
    return dj_timezone.localtime(dj_timezone.now(), timezone=tz).strftime("%Y-%m-%d")


def ucs_filename(short_hostname: str) -> str:
    tz = ZoneInfo(settings.TIME_ZONE)
    stamp = dj_timezone.localtime(dj_timezone.now(), timezone=tz).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", short_hostname.strip().lower())
    safe = re.sub(r"-+", "-", safe).strip("-")[:40] or "host"
    return f"f5-{safe}-{stamp}.ucs"


def windows_scp_config(variant: F5Variant) -> dict | None:
    host = _env_or_setting(
        *_shared_f5_keys("WINDOWS_SCP_HOST"),
        "F5_SCP_HOST",
        "NITROKEY_WINDOWS_SCP_HOST",
    )
    username = _env_or_setting(
        *_shared_f5_keys("WINDOWS_SCP_USERNAME"),
        "F5_SCP_USERNAME",
        "NITROKEY_WINDOWS_SCP_USERNAME",
    )
    password = _env_or_setting(
        *_shared_f5_keys("WINDOWS_SCP_PASSWORD"),
        "F5_SCP_PASSWORD",
        "NITROKEY_WINDOWS_SCP_PASSWORD",
    )
    if not host or not username or not password:
        return None
    port_raw = _env_or_setting(
        *_shared_f5_keys("WINDOWS_SCP_PORT"),
        "F5_SCP_PORT",
        "NITROKEY_WINDOWS_SCP_PORT",
        default="22",
    )
    remote_parent = _env_or_setting(
        *_variant_path_keys(variant, "WINDOWS_SCP_REMOTE_DIR"),
        "F5_SCP_REMOTE_PARENT_DIR",
        "NITROKEY_WINDOWS_SCP_REMOTE_DIR",
    )
    return {
        "host": host,
        "port": int(port_raw) if port_raw else 22,
        "username": username,
        "password": password,
        "remote_parent": remote_parent.replace("\\", "/").rstrip("/"),
    }


def windows_remote_path(config: dict, folder_date: str, filename: str) -> str:
    import posixpath

    parent = config["remote_parent"]
    if parent:
        return posixpath.join(parent, folder_date, filename)
    return posixpath.join(folder_date, filename)


def resolve_standalone_host(job: BackupJob):
    """Host unique pour F5 standalone (DN1, DN2)."""
    if job.equipment_host_id:
        return job.equipment_host
    hosts = list(job.equipment.hosts.order_by("sort_order", "pk"))
    if len(hosts) == 1:
        job.equipment_host = hosts[0]
        job.save(update_fields=["equipment_host"])
        return hosts[0]
    if not hosts:
        raise BackupAdapterError(
            "Aucun host de management configuré (administration → hosts de management)."
        )
    raise BackupAdapterError("Host de management requis.")
