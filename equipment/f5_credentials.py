"""Vérification des identifiants SSH F5 par défaut (.env / fichiers secrets)."""

from django.conf import settings


def default_f5_credentials_configured() -> bool:
    user = getattr(settings, "F5_SSH_USER", "")
    password = getattr(settings, "F5_SSH_PASSWORD", "")
    return bool(user and password)
