"""Vérification des identifiants F5 par défaut (.env / fichiers secrets)."""

from django.conf import settings


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
