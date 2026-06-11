# Types F5-DN1 / F5-DN2 (standalone, sans HA)

from django.db import IntegrityError, migrations


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
        slug = row["slug"]
        fields = {key: value for key, value in row.items() if key != "slug"}
        existing = EquipmentType.objects.filter(slug=slug).first()
        if existing is not None:
            EquipmentType.objects.filter(pk=existing.pk).update(**fields)
            continue
        try:
            EquipmentType.objects.create(slug=slug, **fields)
        except IntegrityError:
            # web + scheduler peuvent lancer migrate en parallèle au démarrage
            EquipmentType.objects.filter(slug=slug).update(**fields)


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
