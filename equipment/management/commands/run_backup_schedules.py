"""Exécute les sauvegardes planifiées arrivées à échéance."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import ProgrammingError
from django.utils import timezone

from equipment.scheduler import process_due_schedules


class Command(BaseCommand):
    help = "Lance les planifications de sauvegarde dont next_run_at est dépassé."

    def handle(self, *args, **options):
        now = timezone.now()
        try:
            jobs = process_due_schedules(now=now)
        except ProgrammingError as exc:
            if "equipment_backupschedule" in str(exc):
                self.stderr.write(
                    "Table equipment_backupschedule absente — exécuter : "
                    "python manage.py migrate"
                )
                return
            raise
        if not jobs:
            self.stdout.write("Aucune planification à exécuter.")
            return
        for job in jobs:
            self.stdout.write(
                f"Job #{job.pk} — {job.equipment} — {job.get_status_display()}"
            )
