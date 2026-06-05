import datetime

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0008_seed_arbor_aed_dc_hosts"),
    ]

    operations = [
        migrations.AddField(
            model_name="backupjob",
            name="trigger",
            field=models.CharField(
                choices=[("manual", "Manuel"), ("scheduled", "Planifié")],
                default="manual",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="BackupSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_enabled", models.BooleanField(default=False, verbose_name="Activée")),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("daily", "Tous les jours"),
                            ("weekly", "Hebdomadaire"),
                            ("monthly", "Mensuel"),
                        ],
                        default="daily",
                        max_length=16,
                    ),
                ),
                (
                    "run_time",
                    models.TimeField(
                        default=datetime.time(2, 0),
                        help_text="Heure d'exécution (fuseau TIME_ZONE / DJANGO_TIME_ZONE).",
                    ),
                ),
                (
                    "weekday",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Lundi"),
                            (1, "Mardi"),
                            (2, "Mercredi"),
                            (3, "Jeudi"),
                            (4, "Vendredi"),
                            (5, "Samedi"),
                            (6, "Dimanche"),
                        ],
                        default=0,
                        help_text="Pour la fréquence hebdomadaire.",
                    ),
                ),
                (
                    "day_of_month",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text="Jour du mois (1–28) pour la fréquence mensuelle.",
                    ),
                ),
                ("next_run_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "equipment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="backup_schedule",
                        to="equipment.equipment",
                    ),
                ),
                (
                    "equipment_host",
                    models.ForeignKey(
                        blank=True,
                        help_text="Host ciblé (si plusieurs hosts).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="backup_schedules",
                        to="equipment.equipmenthost",
                    ),
                ),
            ],
            options={
                "verbose_name": "Planification de sauvegarde",
                "verbose_name_plural": "Planifications de sauvegarde",
            },
        ),
    ]
