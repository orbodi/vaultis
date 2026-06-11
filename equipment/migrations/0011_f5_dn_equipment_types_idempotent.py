# Ré-applique la seed F5-DN si 0010 a échoué (duplicate key) alors que les types existent déjà.

from django.db import migrations

from .0010_f5_dn_equipment_types import seed_f5_dn_types


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0010_f5_dn_equipment_types"),
    ]

    operations = [
        migrations.RunPython(seed_f5_dn_types, migrations.RunPython.noop),
    ]
