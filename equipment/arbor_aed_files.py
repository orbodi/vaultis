"""
Classification et organisation des fichiers de backup Arbor AED.

Exemples de noms ::
  arbor-backup-full.20260603T220003Z.manifest
  arbor-backup-full.20260603T220003Z.vol1.difftar.gz
  arbor-backup-full-signatures.20260603T220003Z.sigtar.gz
  arbor-backup-inc.20260603T220003Z.to.20260603T230003Z.manifest
  arbor-backup-new-signatures.20260603T220003Z.to.20260603T230003Z.sigtar.gz
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# full | full-signatures -> full/ ; inc | new-signatures -> inc/
_ARBOR_NAME_RE = re.compile(
    r"^arbor-backup-(?P<kind>full(?:-signatures)?|inc|new-signatures)\.(?P<date>\d{8})T",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ArborBackupFile:
    path: Path
    backup_type: str  # "full" | "inc"
    folder_date: str  # YYYY-MM-DD


def classify_arbor_filename(name: str) -> tuple[str, str] | None:
    """Retourne (backup_type, folder_date) ou None si le nom ne correspond pas."""
    match = _ARBOR_NAME_RE.match(name)
    if not match:
        return None
    kind = match.group("kind").lower()
    backup_type = "full" if kind.startswith("full") else "inc"
    raw_date = match.group("date")
    folder_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    return backup_type, folder_date


def scan_arbor_source(source_dir: Path) -> tuple[list[ArborBackupFile], list[str]]:
    """Liste les fichiers reconnus et les noms ignorés."""
    recognized: list[ArborBackupFile] = []
    skipped: list[str] = []
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Dossier source introuvable : {source_dir}")

    for entry in sorted(source_dir.iterdir()):
        if not entry.is_file():
            continue
        parsed = classify_arbor_filename(entry.name)
        if parsed is None:
            skipped.append(entry.name)
            continue
        backup_type, folder_date = parsed
        recognized.append(
            ArborBackupFile(
                path=entry,
                backup_type=backup_type,
                folder_date=folder_date,
            )
        )
    return recognized, skipped


def organize_into_staging(
    files: list[ArborBackupFile],
    staging_root: Path,
    *,
    move: bool = False,
) -> Path:
    """
    Copie (ou déplace) les fichiers vers staging_root/YYYY-MM-DD/{full|inc}/.
    Retourne staging_root.
    """
    staging_root.mkdir(parents=True, exist_ok=True)
    transfer = shutil.move if move else shutil.copy2

    for item in files:
        dest_dir = staging_root / item.folder_date / item.backup_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / item.path.name
        if dest.exists():
            dest.unlink()
        transfer(str(item.path), dest)

    return staging_root


def distinct_dates(files: list[ArborBackupFile]) -> list[str]:
    return sorted({f.folder_date for f in files})


def archive_from_staging(
    files: list[ArborBackupFile],
    staging_dc: Path,
    archive_root: Path,
) -> int:
    """Copie optionnelle staging → archive locale (après SCP Windows)."""
    archived = 0
    for item in files:
        staging_file = staging_dc / item.folder_date / item.backup_type / item.path.name
        if not staging_file.is_file():
            continue
        dest_dir = archive_root / item.folder_date / item.backup_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / item.path.name
        if dest.exists():
            dest.unlink()
        shutil.copy2(str(staging_file), dest)
        archived += 1
    return archived


def release_processed_files(
    files: list[ArborBackupFile],
    source_dir: Path,
    staging_dc: Path,
) -> int:
    """
    Après SCP Windows réussi : supprime les fichiers incoming et le staging
    pour libérer l'espace disque.
    """
    if not os.access(source_dir, os.W_OK):
        raise PermissionError(
            f"Dossier incoming non writable : {source_dir}. "
            "Le montage Docker incoming doit être en lecture-écriture."
        )

    released = 0
    errors: list[str] = []
    for item in files:
        if not item.path.is_file():
            continue
        try:
            item.path.unlink()
            released += 1
            logger.info("Arbor: fichier source supprimé %s", item.path.name)
        except OSError as exc:
            errors.append(f"{item.path.name}: {exc}")

    if staging_dc.exists():
        shutil.rmtree(staging_dc)

    if errors:
        sample = "; ".join(errors[:3])
        extra = f" (+{len(errors) - 3} autres)" if len(errors) > 3 else ""
        raise OSError(
            f"Libération espace incomplète dans {source_dir} : {sample}{extra}"
        )

    return released


def archive_processed_files(
    files: list[ArborBackupFile],
    source_dir: Path,
    staging_dc: Path,
    *,
    used_move: bool,
    archive_root: Path | None = None,
) -> int:
    """
    Archive les fichiers traités vers archive_root/YYYY-MM-DD/{full|inc}/.
    Copie depuis le staging (ou la source) ; supprime la source incoming si writable.
    """
    root = archive_root if archive_root is not None else source_dir / "archive"
    archived = 0
    source_writable = os.access(source_dir, os.W_OK)
    left_in_incoming = 0

    for item in files:
        staging_file = staging_dc / item.folder_date / item.backup_type / item.path.name
        if used_move and staging_file.is_file():
            src = staging_file
        elif staging_file.is_file():
            src = staging_file
        elif item.path.is_file():
            src = item.path
        else:
            continue

        dest_dir = root / item.folder_date / item.backup_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / item.path.name
        if dest.exists():
            dest.unlink()
        shutil.copy2(str(src), dest)

        if staging_file.is_file() and staging_file != src:
            staging_file.unlink()
        elif staging_file.is_file():
            staging_file.unlink()

        if item.path.is_file():
            if source_writable:
                try:
                    item.path.unlink()
                except OSError as exc:
                    logger.warning(
                        "Arbor: suppression source impossible %s : %s",
                        item.path,
                        exc,
                    )
                    left_in_incoming += 1
            else:
                left_in_incoming += 1

        archived += 1

    if left_in_incoming:
        logger.warning(
            "Arbor: %s fichier(s) restent dans %s (dossier incoming non writable). "
            "Nettoyage manuel sur l'hôte ou ARBOR_AED_ARCHIVE_IN_SOURCE avec montage RW.",
            left_in_incoming,
            source_dir,
        )

    return archived
