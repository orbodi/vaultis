"""
Adaptateur Arbor AED (DDOS) — organisation locale des backups puis transfert SCP.

Un seul host équipement : les DC actifs (ARBOR_AED_ACTIVE_DCS) déterminent quels
dossiers incoming sont traités (DC01, DC02, ou les deux).
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from equipment.arbor_aed_config import (
    arbor_active_dcs,
    arbor_archive_after_upload,
    arbor_archive_root_for_source,
    arbor_move_source_files,
    arbor_remote_parent_for_dc,
    arbor_source_dir_for_dc,
    arbor_staging_for_dc,
    arbor_staging_root,
    assert_arbor_source_readable,
    scp_config_from_settings,
)
from equipment.arbor_aed_files import (
    archive_processed_files,
    distinct_dates,
    organize_into_staging,
    scan_arbor_source,
)
from equipment.scp_transfer import upload_tree

from .base import BackupAdapterError

if TYPE_CHECKING:
    from equipment.models import BackupJob

logger = logging.getLogger(__name__)


class Adapter:
    def run_backup(self, job: BackupJob) -> str:
        active_dcs = arbor_active_dcs()
        staging_job = arbor_staging_root(job.pk)
        if staging_job.exists():
            shutil.rmtree(staging_job)

        scp = scp_config_from_settings()
        dc_summaries: list[str] = []
        total_files = 0
        total_uploaded = 0
        any_processed = False

        for dc in active_dcs:
            source = arbor_source_dir_for_dc(dc)
            files, skipped = scan_arbor_source(source)
            if not files:
                hint = f" ({len(skipped)} ignorés)" if skipped else ""
                logger.info("Arbor AED %s: aucun fichier dans %s%s", dc, source, hint)
                dc_summaries.append(f"{dc}: aucun fichier{hint}")
                continue

            any_processed = True
            assert_arbor_source_readable(source)
            staging_dc = arbor_staging_for_dc(job.pk, dc)
            move_source = arbor_move_source_files()
            try:
                organize_into_staging(files, staging_dc, move=move_source)
            except PermissionError as exc:
                path = getattr(exc, "filename", None) or str(exc)
                raise BackupAdapterError(
                    f"Permission refusée en lecture : {path}. "
                    "Les backups Arbor sur l'hôte sont souvent en 600 (propriétaire uid 1003) "
                    "alors que Vaultis tourne sous uid 1000. "
                    "Sur l'hôte : find /home/mdoman/net-backups -type f -exec chmod 644 {} \\;"
                ) from exc
            dates = distinct_dates(files)
            remote_parent = arbor_remote_parent_for_dc(dc)
            dc_uploaded = 0

            logger.info(
                "Arbor AED %s: %s fichier(s) source=%s remote=%s",
                dc,
                len(files),
                source,
                remote_parent,
            )

            for folder_date in dates:
                for backup_type in ("full", "inc"):
                    local_type_dir = staging_dc / folder_date / backup_type
                    if not local_type_dir.is_dir():
                        continue
                    remote_type_dir = f"{remote_parent}/{folder_date}/{backup_type}"
                    try:
                        count = upload_tree(
                            local_type_dir,
                            remote_type_dir,
                            host=scp["host"],
                            port=scp["port"],
                            username=scp["username"],
                            password=scp["password"],
                        )
                        dc_uploaded += count
                        total_uploaded += count
                        logger.info(
                            "Arbor AED SCP ok dc=%s date=%s type=%s files=%s remote=%s",
                            dc,
                            folder_date,
                            backup_type,
                            count,
                            remote_type_dir,
                        )
                    except Exception as exc:
                        raise BackupAdapterError(
                            f"Transfert SCP échoué pour {dc} / {folder_date} / {backup_type}. "
                            "Voir les logs (timeout Gunicorn si upload très long)."
                        ) from exc

            archived = 0
            if arbor_archive_after_upload():
                try:
                    archived = archive_processed_files(
                        files,
                        source,
                        staging_dc,
                        used_move=move_source,
                        archive_root=arbor_archive_root_for_source(source),
                    )
                    logger.info(
                        "Arbor AED %s: %s fichier(s) archivé(s) dans %s",
                        dc,
                        archived,
                        arbor_archive_root_for_source(source),
                    )
                except OSError as exc:
                    raise BackupAdapterError(
                        f"Archivage local échoué pour {dc} : {exc}"
                    ) from exc

            full_count = sum(1 for f in files if f.backup_type == "full")
            inc_count = sum(1 for f in files if f.backup_type == "inc")
            total_files += len(files)
            part = (
                f"{dc}: {len(files)} fichier(s) (full {full_count}, inc {inc_count}), "
                f"dates {', '.join(dates)}, {dc_uploaded} envoyé(s)"
            )
            if archived:
                part += f", {archived} archivé(s) localement"
            if skipped:
                part += f", {len(skipped)} ignoré(s) en source"
            dc_summaries.append(part)

        if not any_processed:
            raise BackupAdapterError(
                f"Aucun fichier à traiter pour les DC actifs ({', '.join(active_dcs)})."
            )

        inactive = [dc for dc in ("DC01", "DC02") if dc not in active_dcs]
        msg = (
            f"Arbor AED — DC actifs: {', '.join(active_dcs)} — "
            f"{total_files} fichier(s), {total_uploaded} envoyé(s). "
            + " | ".join(dc_summaries)
        )
        if inactive:
            msg += f" (non traités: {', '.join(inactive)})"
        return msg
