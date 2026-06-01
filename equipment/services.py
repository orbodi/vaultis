"""
Orchestration des jobs de sauvegarde via les adaptateurs (equipment.adapters.*).
"""

from django.utils import timezone

from .adapters.base import BackupAdapterError
from .adapters.registry import get_adapter
from .models import BackupJob


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
    except BackupAdapterError as exc:
        job.status = BackupJob.Status.FAILED
        job.message = str(exc)
    except Exception as exc:
        job.status = BackupJob.Status.FAILED
        job.message = "Erreur technique."

    job.finished_at = timezone.now()
    job.save(update_fields=["status", "message", "finished_at"])
