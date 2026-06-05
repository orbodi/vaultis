"""Sérialisation de l'historique des jobs pour l'API JSON."""

from __future__ import annotations

from django.utils import timezone

from .models import BackupJob, Equipment


def recent_jobs_for_equipment(equipment: Equipment, *, limit: int = 5):
    return equipment.backup_jobs.select_related(
        "triggered_by",
        "equipment_host",
    ).order_by("-started_at")[:limit]


def serialize_backup_job(job: BackupJob) -> dict:
    local_started = timezone.localtime(job.started_at)
    status_labels = {
        BackupJob.Status.SUCCESS: "Réussi",
        BackupJob.Status.FAILED: "Échoué",
        BackupJob.Status.RUNNING: "En cours",
        BackupJob.Status.PENDING: "En attente",
    }
    trigger_labels = {
        BackupJob.Trigger.MANUAL: "Manuel",
        BackupJob.Trigger.SCHEDULED: "Planifié",
    }
    return {
        "id": job.pk,
        "started_at": local_started.strftime("%d/%m/%Y %H:%M"),
        "status": job.status,
        "status_label": status_labels.get(job.status, job.status),
        "host": job.equipment_host.address if job.equipment_host else "—",
        "trigger": job.trigger,
        "trigger_label": trigger_labels.get(job.trigger, job.trigger),
        "username": job.triggered_by.username if job.triggered_by else "—",
        "message": job.message or "—",
    }


def jobs_history_payload(equipment: Equipment) -> dict:
    jobs = list(recent_jobs_for_equipment(equipment))
    return {
        "jobs": [serialize_backup_job(j) for j in jobs],
        "has_running": any(j.status == BackupJob.Status.RUNNING for j in jobs),
        "latest_id": jobs[0].pk if jobs else None,
    }
