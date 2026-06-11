from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from equipment.adapters.arbor_aed import Adapter as ArborAedAdapter
from equipment.adapters.base import BackupAdapterError
from equipment.adapters.f5 import Adapter as F5Adapter
from equipment.adapters.nitrokey import Adapter as NitrokeyAdapter
from equipment.f5_credentials import default_f5_credentials_configured
from equipment.arbor_aed_config import (
    arbor_active_dcs,
    arbor_source_dir_for_dc,
    normalize_dc_key,
)
from equipment.arbor_aed_files import (
    archive_processed_files,
    classify_arbor_filename,
    organize_into_staging,
    scan_arbor_source,
)
from equipment.models import BackupJob, Equipment, EquipmentHost, EquipmentType
from equipment.nethsm_credentials import default_nethsm_credentials_configured
from equipment.services import run_backup_job


class DefaultNethsmCredentialsTests(TestCase):
    @override_settings(NITROKEY_NETHSM_USER="backup1", NITROKEY_NETHSM_PASSWORD="secret")
    def test_default_credentials_configured(self):
        self.assertTrue(default_nethsm_credentials_configured())

    @override_settings(NITROKEY_NETHSM_USER="", NITROKEY_NETHSM_PASSWORD="")
    def test_default_credentials_missing(self):
        self.assertFalse(default_nethsm_credentials_configured())


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

    @patch("equipment.adapters.nitrokey._fetch_nethsm_backup", return_value=b"x" * 1024)
    def test_nethsm_transfers_to_windows_dir_when_configured(self, _mock_fetch):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        self.equipment.extra = {"integration": "nethsm"}
        self.equipment.save(update_fields=["extra"])
        job = BackupJob.objects.create(equipment=self.equipment, equipment_host=self.host)
        job._backup_credentials = {"username": "backup1", "password": "secret"}

        with TemporaryDirectory() as local_dir, TemporaryDirectory() as windows_dir:
            with override_settings(
                NITROKEY_BACKUP_ROOT=Path(local_dir),
                NITROKEY_WINDOWS_TRANSFER_DIR=Path(windows_dir),
            ):
                message = NitrokeyAdapter().run_backup(job)

            local_files = list(Path(local_dir).glob("*.bkp"))
            windows_files = list(Path(windows_dir).glob("*.bkp"))
            self.assertEqual(len(local_files), 1)
            self.assertEqual(len(windows_files), 1)
            self.assertEqual(local_files[0].name, windows_files[0].name)
            self.assertEqual(local_files[0].read_bytes(), windows_files[0].read_bytes())
            self.assertIn("transféré", message.lower())

    @patch("equipment.adapters.nitrokey._fetch_nethsm_backup", return_value=b"x" * 1024)
    @patch("equipment.adapters.nitrokey._transfer_to_windows_smb")
    def test_nethsm_transfers_to_windows_smb_when_configured(self, mock_transfer, _mock_fetch):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        self.equipment.extra = {"integration": "nethsm"}
        self.equipment.save(update_fields=["extra"])
        job = BackupJob.objects.create(equipment=self.equipment, equipment_host=self.host)
        job._backup_credentials = {"username": "backup1", "password": "secret"}

        with TemporaryDirectory() as local_dir:
            with override_settings(
                NITROKEY_BACKUP_ROOT=Path(local_dir),
                NITROKEY_WINDOWS_SMB_HOST="win-backup.local",
                NITROKEY_WINDOWS_SMB_SHARE="Backups",
                NITROKEY_WINDOWS_SMB_REMOTE_DIR="NetHSM",
                NITROKEY_WINDOWS_SMB_USERNAME="svc_backup",
                NITROKEY_WINDOWS_SMB_PASSWORD="passw0rd!",
            ):
                message = NitrokeyAdapter().run_backup(job)

        mock_transfer.assert_called_once()
        self.assertIn("transféré", message.lower())

    @patch("equipment.adapters.nitrokey._fetch_nethsm_backup", return_value=b"x" * 1024)
    @patch("equipment.adapters.nitrokey._transfer_to_windows_scp")
    def test_nethsm_transfers_to_windows_scp_when_configured(self, mock_transfer, _mock_fetch):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        self.equipment.extra = {"integration": "nethsm"}
        self.equipment.save(update_fields=["extra"])
        job = BackupJob.objects.create(equipment=self.equipment, equipment_host=self.host)
        job._backup_credentials = {"username": "backup1", "password": "secret"}

        with TemporaryDirectory() as local_dir:
            with override_settings(
                NITROKEY_BACKUP_ROOT=Path(local_dir),
                NITROKEY_TRANSFER_MODE="scp",
                NITROKEY_WINDOWS_SCP_HOST="172.16.12.187",
                NITROKEY_WINDOWS_SCP_PORT=22,
                NITROKEY_WINDOWS_SCP_USERNAME="username",
                NITROKEY_WINDOWS_SCP_PASSWORD="password",
                NITROKEY_WINDOWS_SCP_REMOTE_DIR="E:/NetConfig_Backup",
            ):
                message = NitrokeyAdapter().run_backup(job)

        mock_transfer.assert_called_once()
        self.assertIn("transféré", message.lower())


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

    @patch("equipment.services.get_adapter")
    def test_service_logs_technical_error_with_context(self, mock_get_adapter):
        class BrokenAdapter:
            def run_backup(self, _job):
                raise RuntimeError("boom")

        mock_get_adapter.return_value = BrokenAdapter()
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
            triggered_by=self.user,
        )

        with self.assertLogs("equipment.services", level="ERROR") as logs:
            run_backup_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.FAILED)
        self.assertEqual(job.message, "Erreur technique.")
        joined = "\n".join(logs.output)
        self.assertIn("Backup technical failure", joined)
        self.assertIn(f"job_id={job.pk}", joined)
        self.assertIn("host=wkst-1.example.local", joined)
        self.assertIn("user=ops", joined)


class ArborAedFileTests(TestCase):
    def test_classify_full_manifest(self):
        self.assertEqual(
            classify_arbor_filename("arbor-backup-full.20260603T220003Z.manifest"),
            ("full", "2026-06-03"),
        )

    def test_classify_full_vol(self):
        self.assertEqual(
            classify_arbor_filename("arbor-backup-full.20260603T220003Z.vol1.difftar.gz"),
            ("full", "2026-06-03"),
        )

    def test_classify_full_signatures(self):
        self.assertEqual(
            classify_arbor_filename("arbor-backup-full-signatures.20260603T220003Z.sigtar.gz"),
            ("full", "2026-06-03"),
        )

    def test_classify_inc_manifest(self):
        self.assertEqual(
            classify_arbor_filename(
                "arbor-backup-inc.20260603T220003Z.to.20260603T230003Z.manifest"
            ),
            ("inc", "2026-06-03"),
        )

    def test_classify_new_signatures(self):
        self.assertEqual(
            classify_arbor_filename(
                "arbor-backup-new-signatures.20260603T220003Z.to.20260603T230003Z.sigtar.gz"
            ),
            ("inc", "2026-06-03"),
        )

    def test_classify_unknown(self):
        self.assertIsNone(classify_arbor_filename("random-file.txt"))

    def test_organize_into_staging(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as src_dir, TemporaryDirectory() as staging_dir:
            src = Path(src_dir)
            (src / "arbor-backup-full.20260603T220003Z.manifest").write_bytes(b"a")
            (src / "arbor-backup-inc.20260603T220003Z.to.20260603T230003Z.vol1.difftar.gz").write_bytes(
                b"b"
            )
            files, skipped = scan_arbor_source(src)
            self.assertEqual(len(files), 2)
            self.assertEqual(skipped, [])
            organize_into_staging(files, Path(staging_dir))
            self.assertTrue((Path(staging_dir) / "2026-06-03" / "full" / "arbor-backup-full.20260603T220003Z.manifest").is_file())
            self.assertTrue(
                (
                    Path(staging_dir)
                    / "2026-06-03"
                    / "inc"
                    / "arbor-backup-inc.20260603T220003Z.to.20260603T230003Z.vol1.difftar.gz"
                ).is_file()
            )


class ArborAedDcConfigTests(TestCase):
    def test_normalize_dc_from_label(self):
        self.assertEqual(normalize_dc_key("DC 01"), "DC01")
        self.assertEqual(normalize_dc_key("DC02"), "DC02")

    @override_settings(ARBOR_AED_ACTIVE_DCS="DC01, DC02")
    def test_active_dcs_both(self):
        self.assertEqual(arbor_active_dcs(), ["DC01", "DC02"])

    @override_settings(ARBOR_AED_ACTIVE_DCS="DC02")
    def test_active_dcs_single(self):
        self.assertEqual(arbor_active_dcs(), ["DC02"])

    def test_source_dir_per_dc(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as d1:
            import os

            os.environ["ARBOR_AED_SOURCE_DIR_DC01"] = d1
            try:
                self.assertEqual(arbor_source_dir_for_dc("DC01"), Path(d1))
            finally:
                os.environ.pop("ARBOR_AED_SOURCE_DIR_DC01", None)

    def test_source_dir_prefers_container_when_env_is_host_path(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        import os

        from equipment import arbor_aed_config

        with TemporaryDirectory() as mount:
            container = Path(mount)
            (container / "arbor-backup-full.20260603T220003Z.manifest").write_bytes(b"x")
            with patch.object(
                arbor_aed_config,
                "ARBOR_CONTAINER_SOURCE_DIRS",
                {"DC01": container},
            ):
                os.environ["ARBOR_AED_SOURCE_DIR_DC01"] = "/home/mdoman/net-backups"
                try:
                    resolved = arbor_source_dir_for_dc("DC01")
                finally:
                    os.environ.pop("ARBOR_AED_SOURCE_DIR_DC01", None)
            self.assertEqual(resolved, container)

    def test_source_dir_falls_back_to_container_mount(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        import os

        from equipment import arbor_aed_config

        with TemporaryDirectory() as mount:
            container = Path(mount)
            with patch.object(
                arbor_aed_config,
                "ARBOR_CONTAINER_SOURCE_DIRS",
                {"DC01": container},
            ):
                os.environ["ARBOR_AED_SOURCE_DIR_DC01"] = "/home/mdoman/net-backups"
                try:
                    resolved = arbor_source_dir_for_dc("DC01")
                finally:
                    os.environ.pop("ARBOR_AED_SOURCE_DIR_DC01", None)
            self.assertEqual(resolved, container)


class ArborAedAdapterTests(TestCase):
    @patch("equipment.adapters.arbor_aed.upload_tree", return_value=2)
    def test_run_backup_organizes_and_uploads(self, mock_upload):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        eq_type, _ = EquipmentType.objects.get_or_create(
            slug="ddos-test",
            defaults={
                "name": "Arbor AED test",
                "adapter_key": "equipment.adapters.arbor_aed",
            },
        )
        equipment = Equipment.objects.create(name="AED test", equipment_type=eq_type)
        host = EquipmentHost.objects.create(equipment=equipment, label="AED", address="aed.local")
        job = BackupJob.objects.create(equipment=equipment, equipment_host=host)

        with TemporaryDirectory() as src_dir, TemporaryDirectory() as staging_dir:
            src = Path(src_dir)
            (src / "arbor-backup-full.20260603T220003Z.manifest").write_bytes(b"x")
            import os

            os.environ["ARBOR_AED_SOURCE_DIR_DC01"] = str(src)
            try:
                with override_settings(
                    ARBOR_AED_ACTIVE_DCS="DC01",
                    ARBOR_AED_STAGING_DIR=Path(staging_dir),
                    ARBOR_AED_REMOTE_PARENT_DIRS={"DC01": "E:/Backups/AED/DC01"},
                    NITROKEY_WINDOWS_SCP_HOST="172.16.12.187",
                    NITROKEY_WINDOWS_SCP_USERNAME="user",
                    NITROKEY_WINDOWS_SCP_PASSWORD="pass",
                ):
                    message = ArborAedAdapter().run_backup(job)
            finally:
                os.environ.pop("ARBOR_AED_SOURCE_DIR_DC01", None)

        self.assertIn("Arbor AED", message)
        self.assertIn("DC01", message)
        self.assertIn("2026-06-03", message)
        self.assertIn("archivé(s)", message)
        self.assertFalse(
            (src / "arbor-backup-full.20260603T220003Z.manifest").exists()
        )
        self.assertTrue(
            (
                src
                / "archive"
                / "2026-06-03"
                / "full"
                / "arbor-backup-full.20260603T220003Z.manifest"
            ).is_file()
        )
        mock_upload.assert_called_once()


class ArborArchiveTests(TestCase):
    def test_archive_after_copy_mode(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as src_dir, TemporaryDirectory() as staging_dir:
            src = Path(src_dir)
            staging = Path(staging_dir)
            manifest = src / "arbor-backup-full.20260603T220003Z.manifest"
            manifest.write_bytes(b"data")
            files, _ = scan_arbor_source(src)
            organize_into_staging(files, staging, move=False)

            count = archive_processed_files(files, src, staging, used_move=False)

            self.assertEqual(count, 1)
            self.assertFalse(manifest.exists())
            archived = src / "archive" / "2026-06-03" / "full" / manifest.name
            self.assertTrue(archived.is_file())
            self.assertEqual(archived.read_bytes(), b"data")

    def test_archive_after_move_mode(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as src_dir, TemporaryDirectory() as staging_dir:
            src = Path(src_dir)
            staging = Path(staging_dir)
            manifest = src / "arbor-backup-inc.20260603T220003Z.to.20260603T230003Z.manifest"
            manifest.write_bytes(b"inc")
            files, _ = scan_arbor_source(src)
            organize_into_staging(files, staging, move=True)

            count = archive_processed_files(files, src, staging, used_move=True)

            self.assertEqual(count, 1)
            self.assertFalse(manifest.exists())
            self.assertTrue(
                (
                    src
                    / "archive"
                    / "2026-06-03"
                    / "inc"
                    / manifest.name
                ).is_file()
            )


class BackupScheduleTests(TestCase):
    def setUp(self):
        self.eq_type = EquipmentType.objects.create(
            slug="sched-test",
            name="Sched test",
            adapter_key="equipment.adapters.arbor_aed",
        )
        self.equipment = Equipment.objects.create(
            name="Sched equipment",
            equipment_type=self.eq_type,
        )

    @override_settings(TIME_ZONE="UTC")
    def test_compute_next_run_daily(self):
        import datetime

        from equipment.models import BackupSchedule
        from equipment.scheduler import compute_next_run

        schedule = BackupSchedule(
            equipment=self.equipment,
            frequency=BackupSchedule.Frequency.DAILY,
            run_time=datetime.time(3, 30),
            is_enabled=True,
        )
        after = datetime.datetime(2026, 6, 4, 10, 0, tzinfo=datetime.timezone.utc)
        nxt = compute_next_run(schedule, after=after)
        self.assertEqual(nxt, datetime.datetime(2026, 6, 5, 3, 30, tzinfo=datetime.timezone.utc))

    @override_settings(TIME_ZONE="UTC")
    def test_compute_next_run_weekly(self):
        import datetime

        from equipment.models import BackupSchedule
        from equipment.scheduler import compute_next_run

        schedule = BackupSchedule(
            equipment=self.equipment,
            frequency=BackupSchedule.Frequency.WEEKLY,
            weekday=BackupSchedule.Weekday.WEDNESDAY,
            run_time=datetime.time(8, 0),
            is_enabled=True,
        )
        # 2026-06-04 is Thursday
        after = datetime.datetime(2026, 6, 4, 9, 0, tzinfo=datetime.timezone.utc)
        nxt = compute_next_run(schedule, after=after)
        self.assertEqual(nxt, datetime.datetime(2026, 6, 10, 8, 0, tzinfo=datetime.timezone.utc))

    @override_settings(TIME_ZONE="UTC")
    def test_schedule_summary_weekly(self):
        import datetime

        from equipment.models import BackupSchedule
        from equipment.scheduler import schedule_summary

        schedule = BackupSchedule(
            equipment=self.equipment,
            frequency=BackupSchedule.Frequency.WEEKLY,
            weekday=BackupSchedule.Weekday.MONDAY,
            run_time=datetime.time(2, 15),
        )
        self.assertIn("Lundi", schedule_summary(schedule))
            self.assertIn("02:15", schedule_summary(schedule))


class JobHistoryApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="op", password="pass")
        eq_type = EquipmentType.objects.create(slug="hist", name="Hist", adapter_key="x")
        self.equipment = Equipment.objects.create(name="Eq", equipment_type=eq_type)
        self.job = BackupJob.objects.create(
            equipment=self.equipment,
            trigger=BackupJob.Trigger.SCHEDULED,
            status=BackupJob.Status.SUCCESS,
            message="OK planifié",
        )

    def test_jobs_json_returns_last_five(self):
        from django.urls import reverse

        self.client.login(username="op", password="pass")
        response = self.client.get(reverse("equipment_jobs_json", args=[self.equipment.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["jobs"]), 1)
        self.assertEqual(payload["jobs"][0]["trigger"], "scheduled")
        self.assertEqual(payload["jobs"][0]["message"], "OK planifié")


class DefaultF5CredentialsTests(TestCase):
    @override_settings(F5_SSH_USER="backup-apiuser", F5_SSH_PASSWORD="secret")
    def test_default_credentials_configured(self):
        self.assertTrue(default_f5_credentials_configured())

    @override_settings(F5_SSH_USER="", F5_SSH_PASSWORD="")
    def test_default_credentials_missing(self):
        self.assertFalse(default_f5_credentials_configured())

    @override_settings(
        F5_SSH_USER="",
        F5_SSH_PASSWORD="",
        F5_API_USER="backup-apiuser",
        F5_API_PASSWORD="secret",
    )
    def test_default_credentials_api_alias(self):
        self.assertTrue(default_f5_credentials_configured())


class F5AdapterTests(TestCase):
    def setUp(self):
        self.eq_type, _ = EquipmentType.objects.get_or_create(
            slug="f5-test",
            defaults={
                "name": "F5 test",
                "adapter_key": "equipment.adapters.f5",
            },
        )
        self.equipment = Equipment.objects.create(
            name="F5 BIG-IP test",
            equipment_type=self.eq_type,
            extra={"integration": "demo"},
        )
        self.host = EquipmentHost.objects.create(
            equipment=self.equipment,
            label="F5 prod",
            address="f5-mgmt.example.com",
        )

    @override_settings(DEBUG=True)
    def test_demo_backup_message(self):
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
        )
        message = F5Adapter().run_backup(job)
        self.assertIn("simulée", message.lower())
        self.assertIn("f5-mgmt.example.com", message)

    def test_ssh_requires_credentials(self):
        self.equipment.extra = {"integration": "ssh"}
        self.equipment.save(update_fields=["extra"])
        job = BackupJob.objects.create(
            equipment=self.equipment,
            equipment_host=self.host,
        )
        with self.assertRaises(BackupAdapterError):
            F5Adapter().run_backup(job)

    @patch(
        "equipment.adapters.f5.resolve_active_mgmt_ip_for_job",
        return_value="172.16.11.26",
    )
    @patch("equipment.adapters.f5._F5SSHSession")
    @override_settings(F5_SSH_USER="backup-apiuser", F5_SSH_PASSWORD="pass")
    def test_ssh_saves_ucs_locally(self, mock_session_cls, _mock_active):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        mock_session = mock_session_cls.return_value
        mock_session.__enter__.return_value = mock_session

        with TemporaryDirectory() as backup_dir:
            ucs_path = Path(backup_dir) / "f5-dc01-ltm-20260610-174500.ucs"
            ucs_path.write_bytes(b"ucs-data")
            mock_session.run_backup.return_value = (ucs_path, ucs_path.name)

            with override_settings(F5_BACKUP_ROOT=Path(backup_dir)):
                self.equipment.extra = {"integration": "ssh"}
                self.equipment.save(update_fields=["extra"])
                job = BackupJob.objects.create(
                    equipment=self.equipment,
                    equipment_host=self.host,
                )
                message = F5Adapter().run_backup(job)

        self.assertIn("UCS F5 enregistré", message)
        self.assertIn("f5-dc01-ltm-20260610-174500.ucs", message)
        mock_session.run_backup.assert_called_once()


class F5ConfigTests(TestCase):
    @override_settings(TIME_ZONE="UTC")
    def test_ucs_filename_format(self):
        from equipment.f5_config import ucs_filename

        name = ucs_filename("dc01-ltm")
        self.assertTrue(name.endswith(".ucs"))
        self.assertTrue(name.startswith("f5-dc01-ltm-"))
        parts = name.removesuffix(".ucs").split("-")
        self.assertEqual(len(parts[-2]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[-1]), 6)  # HHMMSS

    def test_windows_remote_path_with_date(self):
        from equipment.f5_config import windows_remote_path

        path = windows_remote_path(
            {"remote_parent": "E:/NetConfig_Backup/DC01/F5"},
            "2026-06-10",
            "f5-dc01-ltm-20260610-174500.ucs",
        )
        self.assertEqual(
            path,
            "E:/NetConfig_Backup/DC01/F5/2026-06-10/f5-dc01-ltm-20260610-174500.ucs",
        )


class F5HaTests(TestCase):
    def setUp(self):
        self.eq_type, _ = EquipmentType.objects.get_or_create(
            slug="f5-ha-test",
            defaults={
                "name": "F5 HA test",
                "adapter_key": "equipment.adapters.f5",
            },
        )
        self.equipment = Equipment.objects.create(
            name="F5 HA pair",
            equipment_type=self.eq_type,
        )
        EquipmentHost.objects.create(
            equipment=self.equipment,
            label="Node A",
            address="172.16.11.26",
            sort_order=0,
        )
        EquipmentHost.objects.create(
            equipment=self.equipment,
            label="Node B",
            address="172.16.11.27",
            sort_order=1,
        )

    def test_ha_peer_addresses_from_hosts(self):
        from equipment.f5_ha import ha_peer_addresses

        job = BackupJob.objects.create(equipment=self.equipment)
        self.assertEqual(
            ha_peer_addresses(job),
            ["172.16.11.26", "172.16.11.27"],
        )

    @patch("equipment.f5_ha.urlopen")
    def test_resolve_active_mgmt_ip(self, mock_urlopen):
        import json
        from io import BytesIO
        from equipment.f5_ha import resolve_active_mgmt_ip

        payload = {
            "items": [
                {
                    "failoverState": "standby",
                    "managementIp": "172.16.11.27",
                },
                {
                    "failoverState": "active",
                    "managementIp": "172.16.11.26",
                },
            ]
        }
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            json.dumps(payload).encode()
        )

        active = resolve_active_mgmt_ip(
            ["172.16.11.26"],
            "backup-apiuser",
            "secret",
            verify_tls=False,
        )
        self.assertEqual(active, "172.16.11.26")
