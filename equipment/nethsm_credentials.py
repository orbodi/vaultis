"""Vérification des identifiants NetHSM par défaut (variables d'environnement / fichiers)."""

from django.conf import settings


def default_nethsm_credentials_configured() -> bool:
    user = getattr(settings, "NITROKEY_NETHSM_USER", "")
    password = getattr(settings, "NITROKEY_NETHSM_PASSWORD", "")
    return bool(user and password)
