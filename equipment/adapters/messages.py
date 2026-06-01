"""Libellés des messages de backup selon le mode Django (dev / prod)."""

from django.conf import settings


def backup_success_message(target: str) -> str:
    """Succès backup local ou démo : « simulée » uniquement si DEBUG=True."""
    if settings.DEBUG:
        return f"Sauvegarde simulée — {target}."
    return f"Sauvegarde — {target}."
