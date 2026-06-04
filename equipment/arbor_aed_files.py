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

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

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
