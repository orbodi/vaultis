"""
Orchestration des jobs de sauvegarde via les adaptateurs (equipment.adapters.*).
"""

import logging

from django.utils import timezone

from .adapters.base import BackupAdapterError
from .adapters.registry import get_adapter
from .models import BackupJob

logger = logging.getLogger(__name__)


def run_backup_job(job: BackupJob, *, credentials: dict | None = None) -> None:
    job.status = BackupJob.Status.RUNNING
    job.message = ""
    job.save(update_fields=["status", "message"])

    if credentials:
        job._backup_credentials = credentials

    adapter = get_adapter(job.equipment.equipment_type.adapter_key)
    try:
        job.message = adapter.run_backup(job)
        job.status = BackupJob.Status.SUCCESS
        logger.info(
            "Backup success job_id=%s equipment_id=%s host=%s user=%s",
            job.pk,
            job.equipment_id,
            getattr(job.equipment_host, "address", ""),
            getattr(job.triggered_by, "username", ""),
        )
    except BackupAdapterError as exc:
        job.status = BackupJob.Status.FAILED
        job.message = str(exc)
        logger.warning(
            "Backup functional failure job_id=%s equipment_id=%s host=%s user=%s reason=%s",
            job.pk,
            job.equipment_id,
            getattr(job.equipment_host, "address", ""),
            getattr(job.triggered_by, "username", ""),
            exc,
        )
    except Exception as exc:
        job.status = BackupJob.Status.FAILED
        job.message = "Erreur technique."
        logger.exception(
            "Backup technical failure job_id=%s equipment_id=%s host=%s user=%s error=%s",
            job.pk,
            job.equipment_id,
            getattr(job.equipment_host, "address", ""),
            getattr(job.triggered_by, "username", ""),
            exc,
        )

    job.finished_at = timezone.now()
    job.save(update_fields=["status", "message", "finished_at"])
