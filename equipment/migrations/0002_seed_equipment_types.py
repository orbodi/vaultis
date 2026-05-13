# Generated manually for seed data

from django.db import migrations


def seed_types(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    defaults = [
        {
            "slug": "f5",
            "name": "F5 BIG-IP",
            "description": "LTM / ADC — export UCS ou API TMOS.",
            "adapter_key": "equipment.adapters.f5",
        },
        {
            "slug": "palo-alto",
            "name": "Palo Alto Networks",
            "description": "Pare-feu PAN-OS / Panorama.",
            "adapter_key": "equipment.adapters.palo_alto",
        },
        {
            "slug": "ddos",
            "name": "Protection DDoS",
            "description": "Plateforme anti-DDoS (fabricant à paramétrer).",
            "adapter_key": "equipment.adapters.ddos",
        },
        {
            "slug": "nitrokey",
            "name": "Nitrokey",
            "description": "Clé matérielle / procédures spécifiques.",
            "adapter_key": "equipment.adapters.nitrokey",
        },
    ]
    for row in defaults:
        EquipmentType.objects.update_or_create(slug=row["slug"], defaults=row)


def unseed_types(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    EquipmentType.objects.filter(
        slug__in=["f5", "palo-alto", "ddos", "nitrokey"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
