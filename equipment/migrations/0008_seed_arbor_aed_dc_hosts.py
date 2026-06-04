# Hosts DC01 / DC02 pour l'équipement Arbor AED de démo.

from django.db import migrations

ARBOR_EQUIPMENT_NAME = "Protection DDoS - périmètre"

DC_HOSTS = [
    {"label": "DC01", "address": "dc01-aed.local", "sort_order": 0},
    {"label": "DC02", "address": "dc02-aed.local", "sort_order": 1},
]


def seed_arbor_dc_hosts(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    eq = Equipment.objects.filter(name=ARBOR_EQUIPMENT_NAME).first()
    if not eq:
        return
    extra = getattr(eq, "extra", None) or {}
    if not isinstance(extra, dict) or not extra.get("_seed_demo"):
        return
    for row in DC_HOSTS:
        EquipmentHost.objects.get_or_create(
            equipment_id=eq.pk,
            label=row["label"],
            defaults={"address": row["address"], "sort_order": row["sort_order"]},
        )


def unseed_arbor_dc_hosts(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    eq = Equipment.objects.filter(name=ARBOR_EQUIPMENT_NAME).first()
    if not eq:
        return
    labels = [h["label"] for h in DC_HOSTS]
    EquipmentHost.objects.filter(equipment_id=eq.pk, label__in=labels).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0007_arbor_aed_equipment_type"),
    ]

    operations = [
        migrations.RunPython(seed_arbor_dc_hosts, unseed_arbor_dc_hosts),
    ]
