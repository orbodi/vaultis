"""Contrat commun des adaptateurs de sauvegarde."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from equipment.models import BackupJob


class BackupAdapterError(Exception):
    """Échec métier ou technique lors d'un backup."""


class BackupAdapter(Protocol):
    def run_backup(self, job: BackupJob) -> str:
        """Exécute le backup et renvoie un message de succès (affiché sur le job)."""
        ...
