import django.db.models.deletion
from django.db import migrations, models


def copy_hosts_forward(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    for eq in Equipment.objects.all():
        address = (getattr(eq, "host", None) or "").strip()
        if not address:
            continue
        if EquipmentHost.objects.filter(equipment_id=eq.pk).exists():
            continue
        EquipmentHost.objects.create(
            equipment_id=eq.pk,
            label="",
            address=address,
            sort_order=0,
        )


def copy_hosts_backward(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    for eq in Equipment.objects.all():
        first = (
            EquipmentHost.objects.filter(equipment_id=eq.pk)
            .order_by("sort_order", "pk")
            .first()
        )
        eq.host = first.address if first else ""
        eq.save(update_fields=["host"])
    EquipmentHost.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0003_seed_demo_equipments"),
    ]

    operations = [
        migrations.CreateModel(
            name="EquipmentHost",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        blank=True,
                        help_text="Libellé dans les listes (ex. DC principal, DR).",
                        max_length=128,
                    ),
                ),
                (
                    "address",
                    models.CharField(
                        help_text="FQDN ou adresse IP de management.",
                        max_length=255,
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(default=0),
                ),
                (
                    "equipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hosts",
                        to="equipment.equipment",
                    ),
                ),
            ],
            options={
                "verbose_name": "Host de management",
                "verbose_name_plural": "Hosts de management",
                "ordering": ["sort_order", "pk"],
            },
        ),
        migrations.AddField(
            model_name="backupjob",
            name="equipment_host",
            field=models.ForeignKey(
                blank=True,
                help_text="Host ciblé pour ce job (si applicable).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="backup_jobs",
                to="equipment.equipmenthost",
            ),
        ),
        migrations.RunPython(copy_hosts_forward, copy_hosts_backward),
        migrations.RemoveField(
            model_name="equipment",
            name="host",
        ),
    ]
