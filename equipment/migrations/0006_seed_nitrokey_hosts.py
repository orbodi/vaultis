# Hosts de démo pour Nitrokey — active le sélecteur sur la fiche détail.

from django.db import migrations


NITROKEY_EQUIPMENT_NAME = "Nitrokey - parc matériel"

DEMO_HOSTS = [
    {"label": "Poste 045", "address": "wkst-045.example.local", "sort_order": 0},
    {"label": "Poste 112", "address": "wkst-112.example.local", "sort_order": 1},
]


def seed_nitrokey_hosts(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    eq = Equipment.objects.filter(name=NITROKEY_EQUIPMENT_NAME).first()
    if not eq:
        return
    extra = getattr(eq, "extra", None) or {}
    if not isinstance(extra, dict) or not extra.get("_seed_demo"):
        return
    if EquipmentHost.objects.filter(equipment_id=eq.pk).exists():
        return
    for row in DEMO_HOSTS:
        EquipmentHost.objects.create(equipment_id=eq.pk, **row)


def unseed_nitrokey_hosts(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    eq = Equipment.objects.filter(name=NITROKEY_EQUIPMENT_NAME).first()
    if not eq:
        return
    addresses = [h["address"] for h in DEMO_HOSTS]
    EquipmentHost.objects.filter(equipment_id=eq.pk, address__in=addresses).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0005_demo_f5_second_host"),
    ]

    operations = [
        migrations.RunPython(seed_nitrokey_hosts, unseed_nitrokey_hosts),
    ]
