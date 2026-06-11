"""
Adaptateur F5 BIG-IP (cluster HA) — sauvegarde UCS via SSH.

1. API iControl : détection du membre actif
2. Connexion SSH → tmsh save sys ucs
3. SFTP → backup local
4. tmsh delete sys ucs
5. SCP optionnel Windows
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from equipment.f5_config import normalize_mgmt_host
from equipment.f5_ha import ha_peer_addresses, resolve_active_mgmt_ip_for_job
from equipment.f5_variant import F5, integration_mode, raise_unless_demo_allowed

from .base import BackupAdapterError
from .f5_ssh_core import run_f5_ssh_backup
from .messages import backup_success_message

if TYPE_CHECKING:
    from equipment.models import BackupJob

logger = logging.getLogger(__name__)


def _attach_resolved_host(job: BackupJob, active_ip: str) -> str:
    for host in job.equipment.hosts.order_by("sort_order", "pk"):
        if normalize_mgmt_host(host.address) == active_ip:
            job.equipment_host = host
            job.save(update_fields=["equipment_host"])
            return host.label.strip() or active_ip
    return active_ip


class Adapter:
    def run_backup(self, job: BackupJob) -> str:
        mode = integration_mode(job, F5)
        if mode == "ssh":
            return self._run_ssh(job)
        peers = ha_peer_addresses(job)
        return self._run_demo("", peers[0])

    def _run_demo(self, label: str, address: str) -> str:
        raise_unless_demo_allowed()
        target = address
        if label.strip():
            target = f"{label.strip()} ({address})"
        return backup_success_message(target)

    def _run_ssh(self, job: BackupJob) -> str:
        from equipment.f5_credentials import f5_credentials

        logger.info("F5 backup start job_id=%s equipment_id=%s", job.pk, job.equipment_id)
        user, password, _ = f5_credentials(job)
        active_ip = resolve_active_mgmt_ip_for_job(job, user, password)
        host_label = _attach_resolved_host(job, active_ip)
        return run_f5_ssh_backup(job, F5, active_ip, host_label)
