"""Base adaptateur F5 standalone (un seul appliance, sans HA)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from equipment.f5_config import normalize_mgmt_host
from equipment.f5_variant import (
    F5Variant,
    integration_mode,
    raise_unless_demo_allowed,
    resolve_standalone_host,
)

from .f5_ssh_core import run_f5_ssh_backup
from .messages import backup_success_message

if TYPE_CHECKING:
    from equipment.models import BackupJob

logger = logging.getLogger(__name__)


class StandaloneF5Adapter:
    variant: F5Variant

    def run_backup(self, job: BackupJob) -> str:
        mode = integration_mode(job, self.variant)
        equipment_host = resolve_standalone_host(job)
        address = normalize_mgmt_host(equipment_host.address)
        label = equipment_host.label.strip() or address

        if mode == "ssh":
            logger.info(
                "%s backup start job_id=%s equipment_id=%s target=%s",
                self.variant.label,
                job.pk,
                job.equipment_id,
                address,
            )
            return run_f5_ssh_backup(job, self.variant, address, label)

        raise_unless_demo_allowed()
        target = f"{label} ({address})" if label != address else address
        return backup_success_message(target)
