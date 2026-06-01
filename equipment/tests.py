from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from equipment.adapters.base import BackupAdapterError
from equipment.adapters.nitrokey import Adapter as NitrokeyAdapter
from equipment.models import BackupJob, Equipment, EquipmentHost, EquipmentType
from equipment.services import run_backup_job


class NitrokeyAdapterTests(TestCase):
    def setUp(self):
        self.eq_type, _ = EquipmentType.objects.get_or_create(
            slug="nitrokey-test",
            defaults={
                "name": "Nitrokey test",
                "adapter_key": "equipment.adapters.nitrokey",
            },
        )
        self.equipment = Equipment.objects.create(
            name="Nitrokey test",
            equipment_type=self.eq_type,
            extra={"integration": "demo"},
        )
        self.host = EquipmentHost.objects.create(
            equipment=self.equipment,
            label="Poste test",
            address="wkst-test.example.local",
        )

    @override_settings(DEBUG=True)
    def test_demo_backup_message_dev(self):
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
        )
        message = NitrokeyAdapter().run_backup(job)
        self.assertIn("simulée", message.lower())
        self.assertIn("wkst-test.example.local", message)

    @override_settings(DEBUG=False)
    def test_demo_backup_message_prod(self):
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
        )
        message = NitrokeyAdapter().run_backup(job)
        self.assertNotIn("simulée", message.lower())
        self.assertIn("Sauvegarde —", message)
        self.assertIn("wkst-test.example.local", message)

    def test_nethsm_requires_credentials(self):
        self.equipment.extra = {"integration": "nethsm"}
        self.equipment.save(update_fields=["extra"])
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
        )
        with self.assertRaises(BackupAdapterError) as ctx:
            NitrokeyAdapter().run_backup(job)
        self.assertIn("Identifiants API requis", str(ctx.exception))

    @patch("equipment.adapters.nitrokey._fetch_nethsm_backup", return_value=b"x" * 2048)
    def test_nethsm_uses_form_credentials(self, mock_fetch):
        self.equipment.extra = {"integration": "demo"}
        self.equipment.save(update_fields=["extra"])
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
        )
        job._backup_credentials = {
            "username": "backup1",
            "password": "NH$mBrz7@4y56CBt",
        }
        message = NitrokeyAdapter().run_backup(job)
        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args[0][0], "wkst-test.example.local")
        self.assertEqual(mock_fetch.call_args[0][1], "backup1")
        self.assertEqual(mock_fetch.call_args[0][2], "NH$mBrz7@4y56CBt")
        self.assertIn("Backup enregistré", message)

    def test_api_base_from_host_ip(self):
        from equipment.adapters.nitrokey import _api_base

        self.assertEqual(_api_base("172.16.42.112"), "https://172.16.42.112/api/v1")

    def test_backup_filename_is_timestamped(self):
        from equipment.adapters.nitrokey import _backup_filename

        name = _backup_filename("172.16.42.112")
        self.assertTrue(name.endswith("_nethsm_172_16_42_112.bkp"))
        self.assertRegex(name, r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_nethsm_")

    @patch("equipment.adapters.nitrokey.urlopen")
    def test_nethsm_backup_request_matches_curl(self, mock_urlopen):
        from equipment.adapters.nitrokey import _fetch_nethsm_backup

        mock_urlopen.return_value.__enter__.return_value.read.return_value = b"backup-bytes"
        _fetch_nethsm_backup("172.16.42.112", "backup1", "p@ss", verify_tls=False)
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://172.16.42.112/api/v1/system/backup")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Accept"), "application/octet-stream")
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))


class RunBackupJobTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ops", password="x")
        self.eq_type, _ = EquipmentType.objects.get_or_create(
            slug="nitrokey-svc",
            defaults={
                "name": "Nitrokey",
                "adapter_key": "equipment.adapters.nitrokey",
            },
        )
        self.equipment = Equipment.objects.create(
            name="Nitrokey service",
            equipment_type=self.eq_type,
            extra={"integration": "demo"},
        )
        self.host = EquipmentHost.objects.create(
            equipment=self.equipment,
            label="P1",
            address="wkst-1.example.local",
        )

    def test_service_uses_nitrokey_adapter(self):
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
            triggered_by=self.user,
        )
        run_backup_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.SUCCESS)
        self.assertIn("simulée", job.message.lower())
        self.assertIsNotNone(job.finished_at)
