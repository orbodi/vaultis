# Host de démo supplémentaire pour illustrer le sélecteur multi-hosts sur la fiche F5.

from django.db import migrations


def add_dr_host_for_demo_f5(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    eq = Equipment.objects.filter(name="F5 BIG-IP - Production").first()
    if not eq:
        return
    extra = getattr(eq, "extra", None) or {}
    if not isinstance(extra, dict) or not extra.get("_seed_demo"):
        return
    if EquipmentHost.objects.filter(equipment_id=eq.pk).count() >= 2:
        return
    EquipmentHost.objects.create(
        equipment_id=eq.pk,
        label="Site DR",
        address="f5-mgmt-dr.example.com",
        sort_order=1,
    )


def remove_dr_host(apps, schema_editor):
    EquipmentHost = apps.get_model("equipment", "EquipmentHost")
    EquipmentHost.objects.filter(
        address="f5-mgmt-dr.example.com",
        label="Site DR",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0004_equipmenthost_remove_equipment_host"),
    ]

    operations = [
        migrations.RunPython(add_dr_host_for_demo_f5, remove_dr_host),
    ]
