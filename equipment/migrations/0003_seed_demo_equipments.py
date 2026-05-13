# Données de démo : une carte par type d’équipement (si aucun n’existe pour ce type).

from django.db import migrations


def seed_demo_equipments(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentType = apps.get_model("equipment", "EquipmentType")

    rows = [
        (
            "f5",
            "F5 BIG-IP - Production",
            "f5-mgmt.example.com",
            {"partition": "Common"},
        ),
        (
            "palo-alto",
            "Palo Alto - Pare-feu principal",
            "pa-fw01.example.com",
            {"panorama": False},
        ),
        (
            "ddos",
            "Protection DDoS - périmètre",
            "ddos-scrub.example.com",
            {"site": "edge"},
        ),
        (
            "nitrokey",
            "Nitrokey - parc matériel",
            "",
            {"note": "Sauvegarde / export selon modèle (USB)."},
        ),
    ]

    for slug, name, host, extra in rows:
        try:
            et = EquipmentType.objects.get(slug=slug)
        except EquipmentType.DoesNotExist:
            continue
        if Equipment.objects.filter(equipment_type=et).exists():
            continue
        merged_extra = {**extra, "_seed_demo": True}
        Equipment.objects.create(
            name=name,
            equipment_type=et,
            host=host,
            extra=merged_extra,
        )


def unseed_demo_equipments(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    Equipment.objects.filter(extra__contains={"_seed_demo": True}).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0002_seed_equipment_types"),
    ]

    operations = [
        migrations.RunPython(seed_demo_equipments, unseed_demo_equipments),
    ]
