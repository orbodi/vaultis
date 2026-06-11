# Types F5-DN1 / F5-DN2 (standalone, sans HA)

from django.db import migrations


def seed_f5_dn_types(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    rows = [
        {
            "slug": "f5-dn1",
            "name": "F5 BIG-IP DN1",
            "description": "F5 standalone DN1 — sauvegarde UCS SSH (sans cluster HA).",
            "adapter_key": "equipment.adapters.f5_dn1",
        },
        {
            "slug": "f5-dn2",
            "name": "F5 BIG-IP DN2",
            "description": "F5 standalone DN2 — sauvegarde UCS SSH (sans cluster HA).",
            "adapter_key": "equipment.adapters.f5_dn2",
        },
    ]
    for row in rows:
        EquipmentType.objects.update_or_create(slug=row["slug"], defaults=row)


def unseed_f5_dn_types(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    EquipmentType.objects.filter(slug__in=["f5-dn1", "f5-dn2"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0009_backup_schedule"),
    ]

    operations = [
        migrations.RunPython(seed_f5_dn_types, unseed_f5_dn_types),
    ]
