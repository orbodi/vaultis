from django.db import migrations


def update_ddos_type(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    EquipmentType.objects.filter(slug="ddos").update(
        name="Arbor AED",
        description=(
            "NETSCOUT Arbor Edge Defense — classement des fichiers arbor-backup-* "
            "et archivage SCP vers dossier distant."
        ),
        adapter_key="equipment.adapters.arbor_aed",
    )


def revert_ddos_type(apps, schema_editor):
    EquipmentType = apps.get_model("equipment", "EquipmentType")
    EquipmentType.objects.filter(slug="ddos").update(
        name="Protection DDoS",
        description="Plateforme anti-DDoS (fabricant à paramétrer).",
        adapter_key="equipment.adapters.ddos",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0006_seed_nitrokey_hosts"),
    ]

    operations = [
        migrations.RunPython(update_ddos_type, revert_ddos_type),
    ]
