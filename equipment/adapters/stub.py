"""Adaptateur générique pour les types non encore branchés sur une API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .messages import backup_success_message

if TYPE_CHECKING:
    from equipment.models import BackupJob


class Adapter:
    def __init__(self, adapter_key: str = "") -> None:
        self._adapter_key = adapter_key

    def run_backup(self, job: BackupJob) -> str:
        target_host = (
            job.equipment_host.address if job.equipment_host_id else "—"
        )
        return backup_success_message(target_host)
