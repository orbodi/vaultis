"""Chargement dynamique des adaptateurs via EquipmentType.adapter_key."""

from __future__ import annotations

import importlib
import logging

from .base import BackupAdapter
from .stub import Adapter as StubAdapter

logger = logging.getLogger(__name__)


def get_adapter(adapter_key: str) -> BackupAdapter:
    key = (adapter_key or "").strip()
    if not key:
        logger.warning("Adaptateur vide — stub utilisé (échec en production).")
        return StubAdapter()
    try:
        module = importlib.import_module(key)
    except ImportError:
        logger.warning("Adaptateur introuvable %r — stub utilisé.", key)
        return StubAdapter(key)
    adapter_cls = getattr(module, "Adapter", None)
    if adapter_cls is None:
        logger.warning("Classe Adapter absente dans %r — stub utilisé.", key)
        return StubAdapter(key)
    return adapter_cls()
