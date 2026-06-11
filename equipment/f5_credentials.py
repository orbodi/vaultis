"""Identifiants F5 (.env / formulaire / extra)."""

from __future__ import annotations

from django.conf import settings

from .adapters.base import BackupAdapterError
from .models import BackupJob


def env_f5_user_password() -> tuple[str, str]:
    """Même couple user/password pour l'API HA et le SSH (F5_SSH_* ou F5_API_*)."""
    ssh_user = (getattr(settings, "F5_SSH_USER", "") or "").strip()
    ssh_password = getattr(settings, "F5_SSH_PASSWORD", "") or ""
    api_user = (getattr(settings, "F5_API_USER", "") or "").strip()
    api_password = getattr(settings, "F5_API_PASSWORD", "") or ""
    return ssh_user or api_user, ssh_password or api_password


def default_f5_credentials_configured() -> bool:
    user, password = env_f5_user_password()
    return bool(user and password)


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

    user, password = env_f5_user_password()
    if not user or not password:
        raise BackupAdapterError("Identifiants F5 requis.")
    return user, password, "env"
