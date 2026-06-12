# Corrige les types F5-DN mal créés à la main (ex. slug=dns, adapter_key vide).

from django.db import migrations


def _ensure_dn_types(EquipmentType):
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
    by_slug = {}
    for row in rows:
        slug = row["slug"]
        fields = {key: value for key, value in row.items() if key != "slug"}
        obj, _ = EquipmentType.objects.update_or_create(slug=slug, defaults=fields)
        by_slug[slug] = obj
    return by_slug


def fix_misconfigured_types(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    Equipment = apps.get_model("equipment", "Equipment")

    dn_types = _ensure_dn_types(EquipmentType)

    # Slugs créés à la main, souvent sans adapter_key
    reassign_to_dn2 = ("dns", "f5dn", "f5-dn", "f5_dn", "f5dn2")
    reassign_to_dn1 = ("f5dn1",)

    for slug in reassign_to_dn2:
        wrong = EquipmentType.objects.filter(slug=slug).first()
        if wrong is None:
            continue
        if (wrong.adapter_key or "").strip():
            continue
        Equipment.objects.filter(equipment_type=wrong).update(
            equipment_type=dn_types["f5-dn2"],
        )
        if not Equipment.objects.filter(equipment_type=wrong).exists():
            wrong.delete()

    for slug in reassign_to_dn1:
        wrong = EquipmentType.objects.filter(slug=slug).first()
        if wrong is None:
            continue
        if (wrong.adapter_key or "").strip():
            continue
        Equipment.objects.filter(equipment_type=wrong).update(
            equipment_type=dn_types["f5-dn1"],
        )
        if not Equipment.objects.filter(equipment_type=wrong).exists():
            wrong.delete()

    # Types restants avec adapter_key vide : signaler via mise à jour si slug ressemble à F5 DN
    for et in EquipmentType.objects.filter(adapter_key=""):
        slug = (et.slug or "").lower()
        if "dn1" in slug or slug.endswith("-dn1"):
            et.adapter_key = "equipment.adapters.f5_dn1"
            et.save(update_fields=["adapter_key"])
        elif "dn2" in slug or slug.endswith("-dn2") or slug == "dns":
            et.adapter_key = "equipment.adapters.f5_dn2"
            et.save(update_fields=["adapter_key"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0010_f5_dn_equipment_types"),
    ]

    operations = [
        migrations.RunPython(fix_misconfigured_types, noop),
    ]
