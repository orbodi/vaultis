"""Chargement dynamique des adaptateurs via EquipmentType.adapter_key."""

from __future__ import annotations

import importlib

from .base import BackupAdapter
from .stub import Adapter as StubAdapter


def get_adapter(adapter_key: str) -> BackupAdapter:
    key = (adapter_key or "").strip()
    if not key:
        return StubAdapter()
    try:
        module = importlib.import_module(key)
    except ImportError:
        return StubAdapter(key)
    adapter_cls = getattr(module, "Adapter", None)
    if adapter_cls is None:
        return StubAdapter(key)
    return adapter_cls()
