import datetime

from django.conf import settings
from django.db import models


class EquipmentType(models.Model):
    """Type d'équipement extensible (F5, Palo Alto, etc.)."""

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    adapter_key = models.CharField(
        max_length=256,
        blank=True,
        help_text="Identifiant du module Python qui pilotera l'API (ex. equipment.adapters.f5).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Type d'équipement"
        verbose_name_plural = "Types d'équipement"

    def __str__(self) -> str:
        return self.name


class Equipment(models.Model):
    name = models.CharField(max_length=255)
    equipment_type = models.ForeignKey(
        EquipmentType,
        on_delete=models.PROTECT,
        related_name="equipments",
    )
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Équipement"
        verbose_name_plural = "Équipements"

    def __str__(self) -> str:
        return self.name

    def last_backup_job(self):
        return self.backup_jobs.order_by("-started_at").first()


class EquipmentHost(models.Model):
    """Point de management (FQDN / IP) rattaché à un équipement — plusieurs par actif."""

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="hosts",
    )
    label = models.CharField(
        max_length=128,
        blank=True,
        help_text="Libellé dans les listes (ex. DC principal, DR).",
    )
    address = models.CharField(
        max_length=255,
        help_text="FQDN ou adresse IP de management.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Host de management"
        verbose_name_plural = "Hosts de management"

    def __str__(self) -> str:
        if self.label.strip():
            return f"{self.label.strip()} ({self.address})"
        return self.address

    def select_display(self) -> str:
        if self.label.strip():
            return f"{self.label.strip()} — {self.address}"
        return self.address


class BackupSchedule(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Tous les jours"
        WEEKLY = "weekly", "Hebdomadaire"
        MONTHLY = "monthly", "Mensuel"

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Lundi"
        TUESDAY = 1, "Mardi"
        WEDNESDAY = 2, "Mercredi"
        THURSDAY = 3, "Jeudi"
        FRIDAY = 4, "Vendredi"
        SATURDAY = 5, "Samedi"
        SUNDAY = 6, "Dimanche"

    equipment = models.OneToOneField(
        Equipment,
        on_delete=models.CASCADE,
        related_name="backup_schedule",
    )
    is_enabled = models.BooleanField(default=False, verbose_name="Activée")
    frequency = models.CharField(
        max_length=16,
        choices=Frequency.choices,
        default=Frequency.DAILY,
    )
    run_time = models.TimeField(
        default=datetime.time(2, 0),
        help_text="Heure d'exécution (fuseau TIME_ZONE / DJANGO_TIME_ZONE).",
    )
    weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices,
        default=Weekday.MONDAY,
        help_text="Pour la fréquence hebdomadaire.",
    )
    day_of_month = models.PositiveSmallIntegerField(
        default=1,
        help_text="Jour du mois (1–28) pour la fréquence mensuelle.",
    )
    equipment_host = models.ForeignKey(
        "EquipmentHost",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_schedules",
        help_text="Host ciblé (si plusieurs hosts).",
    )
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Planification de sauvegarde"
        verbose_name_plural = "Planifications de sauvegarde"

    def __str__(self) -> str:
        state = "activée" if self.is_enabled else "désactivée"
        return f"Planification {self.equipment} ({state})"


class BackupJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        SUCCESS = "success", "Réussi"
        FAILED = "failed", "Échoué"

    class Trigger(models.TextChoices):
        MANUAL = "manual", "Manuel"
        SCHEDULED = "scheduled", "Planifié"

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="backup_jobs",
    )
    equipment_host = models.ForeignKey(
        "EquipmentHost",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_jobs",
        help_text="Host ciblé pour ce job (si applicable).",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    trigger = models.CharField(
        max_length=16,
        choices=Trigger.choices,
        default=Trigger.MANUAL,
    )
    message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_jobs",
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Sauvegarde (job)"
        verbose_name_plural = "Sauvegardes (jobs)"

    def __str__(self) -> str:
        return f"{self.equipment} — {self.get_status_display()} ({self.started_at:%Y-%m-%d %H:%M})"
