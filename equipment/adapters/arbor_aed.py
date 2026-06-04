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
    arbor_move_source_files,
    arbor_remote_parent_for_dc,
    arbor_source_dir_for_dc,
    arbor_staging_for_dc,
    arbor_staging_root,
    scp_config_from_settings,
)
from equipment.arbor_aed_files import (
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
            staging_dc = arbor_staging_for_dc(job.pk, dc)
            organize_into_staging(files, staging_dc, move=arbor_move_source_files())
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
                local_date_dir = staging_dc / folder_date
                remote_date_dir = f"{remote_parent}/{folder_date}"
                try:
                    count = upload_tree(
                        local_date_dir,
                        remote_date_dir,
                        host=scp["host"],
                        port=scp["port"],
                        username=scp["username"],
                        password=scp["password"],
                    )
                    dc_uploaded += count
                    total_uploaded += count
                    logger.info(
                        "Arbor AED SCP ok dc=%s date=%s files=%s remote=%s",
                        dc,
                        folder_date,
                        count,
                        remote_date_dir,
                    )
                except Exception as exc:
                    raise BackupAdapterError(
                        f"Transfert SCP échoué pour {dc} / {folder_date}. Voir les logs."
                    ) from exc

            full_count = sum(1 for f in files if f.backup_type == "full")
            inc_count = sum(1 for f in files if f.backup_type == "inc")
            total_files += len(files)
            part = (
                f"{dc}: {len(files)} fichier(s) (full {full_count}, inc {inc_count}), "
                f"dates {', '.join(dates)}, {dc_uploaded} envoyé(s)"
            )
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
