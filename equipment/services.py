"""
Logique d'orchestration des backups. Pour l'instant : stub à remplacer par les appels API réels.
"""

from django.utils import timezone

from .models import BackupJob


def run_backup_job(job: BackupJob) -> None:
    """
    Exécute (ou enfile) un job. MVP : succès immédiat avec message explicite.
    Remplacer par adaptateur selon job.equipment.equipment_type.adapter_key.
    """
    job.status = BackupJob.Status.RUNNING
    job.message = ""
    job.save(update_fields=["status", "message"])

    # TODO: brancher l'adaptateur (F5, Palo, etc.)
    job.status = BackupJob.Status.SUCCESS
    job.message = (
        "Sauvegarde simulée : brancher l'API de l'équipement "
        f"({job.equipment.equipment_type.slug})."
    )
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "message", "finished_at"])
