"""Base adaptateur F5 standalone (un seul appliance, sans HA)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from equipment.f5_config import normalize_mgmt_host
from equipment.f5_variant import F5Variant, resolve_standalone_host

from .f5_ssh_core import run_f5_ssh_backup

if TYPE_CHECKING:
    from equipment.models import BackupJob

logger = logging.getLogger(__name__)


class StandaloneF5Adapter:
    """SSH obligatoire — même credentials que le F5 HA, IP directe, sans détection iControl."""

    variant: F5Variant

    def run_backup(self, job: BackupJob) -> str:
        return self._run_ssh(job)

    def _run_ssh(self, job: BackupJob) -> str:
        from equipment.f5_credentials import f5_credentials

        host = resolve_standalone_host(job)
        address = normalize_mgmt_host(host.address)
        label = host.label.strip() or address

        logger.info(
            "%s backup start job_id=%s equipment_id=%s target=%s",
            self.variant.label,
            job.pk,
            job.equipment_id,
            address,
        )
        f5_credentials(job)
        if job.equipment_host_id != host.pk:
            job.equipment_host = host
            job.save(update_fields=["equipment_host"])
        return run_f5_ssh_backup(job, self.variant, address, label)
