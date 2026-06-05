"""Marque comme échoués les jobs restés « En cours » (worker tué, timeout, etc.)."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from equipment.models import BackupJob


class Command(BaseCommand):
    help = "Clôture les sauvegardes bloquées en statut « En cours »."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=30,
            help="Durée max avant de considérer un job comme bloqué (défaut : 30).",
        )

    def handle(self, *args, **options):
        minutes = max(1, int(options["minutes"]))
        cutoff = timezone.now() - timedelta(minutes=minutes)
        stale = BackupJob.objects.filter(
            status=BackupJob.Status.RUNNING,
            started_at__lt=cutoff,
        )
        count = stale.count()
        if not count:
            self.stdout.write("Aucun job bloqué.")
            return

        message = (
            "Job interrompu (timeout ou redémarrage du conteneur). "
            "Relancer la sauvegarde si besoin."
        )
        for job in stale:
            job.status = BackupJob.Status.FAILED
            job.message = message
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "message", "finished_at"])
        self.stdout.write(self.style.WARNING(f"{count} job(s) marqué(s) échoué(s)."))
