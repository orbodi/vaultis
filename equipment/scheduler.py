"""Calcul des prochaines exécutions et lancement des sauvegardes planifiées."""

from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from django.utils import timezone

from .models import BackupJob, BackupSchedule
from .f5_credentials import default_f5_credentials_configured
from .f5_variant import is_f5_family_slug, is_f5_ha_slug
from .nethsm_credentials import default_nethsm_credentials_configured
from .services import run_backup_job

if TYPE_CHECKING:
    from .models import Equipment


def compute_next_run(schedule: BackupSchedule, *, after: datetime.datetime | None = None) -> datetime.datetime:
    """Prochaine exécution strictement après ``after`` (fuseau Django / TIME_ZONE)."""
    after = after or timezone.now()
    tz = timezone.get_current_timezone()
    local_after = timezone.localtime(after)
    run_time = schedule.run_time

    def aware_on(day: datetime.date) -> datetime.datetime:
        naive = datetime.datetime.combine(day, run_time)
        return timezone.make_aware(naive, tz)

    if schedule.frequency == BackupSchedule.Frequency.DAILY:
        candidate = aware_on(local_after.date())
        if candidate <= after:
            candidate = aware_on(local_after.date() + datetime.timedelta(days=1))
        return candidate

    if schedule.frequency == BackupSchedule.Frequency.WEEKLY:
        target = int(schedule.weekday)
        days_ahead = (target - local_after.weekday()) % 7
        candidate = aware_on(local_after.date() + datetime.timedelta(days=days_ahead))
        if candidate <= after:
            candidate = aware_on(
                local_after.date() + datetime.timedelta(days=days_ahead + 7)
            )
        return candidate

    if schedule.frequency == BackupSchedule.Frequency.MONTHLY:
        year, month = local_after.year, local_after.month
        for _ in range(36):
            last_day = calendar.monthrange(year, month)[1]
            day = min(int(schedule.day_of_month), last_day)
            candidate = aware_on(datetime.date(year, month, day))
            if candidate > after:
                return candidate
            month += 1
            if month > 12:
                month = 1
                year += 1

    raise ValueError(f"Fréquence invalide : {schedule.frequency}")


def schedule_summary(schedule: BackupSchedule) -> str:
    """Libellé lisible pour l'interface."""
    time_str = schedule.run_time.strftime("%H:%M")
    if schedule.frequency == BackupSchedule.Frequency.DAILY:
        return f"Tous les jours à {time_str}"
    if schedule.frequency == BackupSchedule.Frequency.WEEKLY:
        day = schedule.get_weekday_display()
        return f"Chaque {day} à {time_str}"
    if schedule.frequency == BackupSchedule.Frequency.MONTHLY:
        return f"Le {schedule.day_of_month} de chaque mois à {time_str}"
    return "—"


def resolve_schedule_host(schedule: BackupSchedule):
    """Host à utiliser pour une exécution planifiée."""
    equipment = schedule.equipment
    if equipment.equipment_type.slug in ("ddos", "f5"):
        return None
    if schedule.equipment_host_id:
        return schedule.equipment_host
    hosts = list(equipment.hosts.order_by("sort_order", "pk"))
    if len(hosts) == 1:
        return hosts[0]
    return None


def validate_schedule_runnable(schedule: BackupSchedule) -> str | None:
    """Retourne un message d'erreur si la planification ne peut pas s'exécuter."""
    equipment = schedule.equipment
    slug = equipment.equipment_type.slug
    if slug == "nitrokey" and not default_nethsm_credentials_configured():
        return (
            "Identifiants NetHSM par défaut non configurés (.env) — "
            "requis pour les sauvegardes planifiées."
        )
    if is_f5_family_slug(slug) and not default_f5_credentials_configured():
        return (
            "Identifiants F5 par défaut non configurés (.env : F5_SSH_* ou F5_API_*) — "
            "requis pour les sauvegardes planifiées."
        )
    if is_f5_ha_slug(slug) and not equipment.hosts.exists():
        return "Aucun nœud de cluster F5 configuré dans l'administration."
    if slug not in ("ddos", "f5"):
        host = resolve_schedule_host(schedule)
        if host is None:
            return "Aucun host configuré ou sélectionné pour la planification."
    return None


def run_scheduled_backup(schedule: BackupSchedule) -> BackupJob:
    """Crée et exécute un job pour cette planification."""
    err = validate_schedule_runnable(schedule)
    if err:
        job = BackupJob.objects.create(
            equipment=schedule.equipment,
            equipment_host=resolve_schedule_host(schedule),
            trigger=BackupJob.Trigger.SCHEDULED,
            status=BackupJob.Status.FAILED,
            message=err,
            finished_at=timezone.now(),
        )
        return job

    equipment_host = resolve_schedule_host(schedule)
    job = BackupJob.objects.create(
        equipment=schedule.equipment,
        equipment_host=equipment_host,
        trigger=BackupJob.Trigger.SCHEDULED,
    )
    run_backup_job(job, credentials=None)
    return job


def process_due_schedules(*, now: datetime.datetime | None = None) -> list[BackupJob]:
    """Lance les planifications arrivées à échéance. Retourne les jobs créés."""
    now = now or timezone.now()
    jobs: list[BackupJob] = []

    due = (
        BackupSchedule.objects.filter(is_enabled=True, next_run_at__lte=now)
        .select_related("equipment", "equipment__equipment_type", "equipment_host")
        .order_by("next_run_at", "pk")
    )

    for schedule in due:
        if BackupJob.objects.filter(
            equipment=schedule.equipment,
            status=BackupJob.Status.RUNNING,
        ).exists():
            continue

        job = run_scheduled_backup(schedule)
        jobs.append(job)
        schedule.last_run_at = now
        schedule.next_run_at = compute_next_run(schedule, after=now)
        schedule.save(update_fields=["last_run_at", "next_run_at", "updated_at"])

    return jobs
