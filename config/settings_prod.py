"""
Paramètres production — charger via DJANGO_SETTINGS_MODULE=config.settings_prod
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401,F403

DEBUG = False

if SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured(
        "Définissez DJANGO_SECRET_KEY (valeur unique) avant de lancer en production."
    )

_allowed = os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip()
if not _allowed:
    raise ImproperlyConfigured(
        "Définissez DJANGO_ALLOWED_HOSTS (ex. vaultis.example.com,127.0.0.1)."
    )
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]

_csrf_origins = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").strip()
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        f"{'https' if os.environ.get('DJANGO_USE_HTTPS', '').lower() in ('1', 'true', 'yes') else 'http'}://{host}"
        for host in ALLOWED_HOSTS
        if host not in ("*",)
    ]

_use_https = os.environ.get("DJANGO_USE_HTTPS", "").lower() in ("1", "true", "yes")
SESSION_COOKIE_SECURE = _use_https
CSRF_COOKIE_SECURE = _use_https
SECURE_SSL_REDIRECT = _use_https
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

_backup_root = os.environ.get("NITROKEY_BACKUP_ROOT", "").strip()
if _backup_root:
    NITROKEY_BACKUP_ROOT = Path(_backup_root)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
