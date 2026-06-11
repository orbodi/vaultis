"""
Orchestration des jobs de sauvegarde via les adaptateurs (equipment.adapters.*).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from django.utils import timezone

from .adapters.base import BackupAdapterError
from .adapters.registry import get_adapter
from .models import BackupJob

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def run_backup_job_async(job_id: int, *, credentials: dict | None = None) -> None:
    """Lance la sauvegarde en arrière-plan (réponse HTTP immédiate)."""

    def _worker() -> None:
        from django.db import close_old_connections

        close_old_connections()
        job = BackupJob.objects.select_related(
            "equipment",
            "equipment__equipment_type",
            "equipment_host",
            "triggered_by",
        ).get(pk=job_id)
        logger.info(
            "Backup worker start job_id=%s equipment_id=%s adapter=%s",
            job.pk,
            job.equipment_id,
            job.equipment.equipment_type.adapter_key,
        )
        run_backup_job(job, credentials=credentials)

    threading.Thread(
        target=_worker,
        name=f"backup-job-{job_id}",
        daemon=True,
    ).start()


def run_backup_job(job: BackupJob, *, credentials: dict | None = None) -> None:
    job.status = BackupJob.Status.RUNNING
    job.message = ""
    job.save(update_fields=["status", "message"])

    if credentials:
        job._backup_credentials = credentials

    logger.info(
        "Backup run start job_id=%s equipment_id=%s host=%s",
        job.pk,
        job.equipment_id,
        getattr(job.equipment_host, "address", ""),
    )

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
