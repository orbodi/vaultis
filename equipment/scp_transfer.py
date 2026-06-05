"""Transfert de fichiers / arborescences vers un hôte Windows via SFTP (SCP)."""

from __future__ import annotations

import logging
import posixpath
from pathlib import Path

logger = logging.getLogger(__name__)


def upload_tree(local_root: Path, remote_parent: str, *, host: str, port: int, username: str, password: str) -> int:
    """
    Envoie récursivement local_root vers remote_parent (chemins POSIX côté SFTP).
    Retourne le nombre de fichiers transférés.
    """
    import paramiko

    if not local_root.is_dir():
        raise FileNotFoundError(f"Dossier local introuvable : {local_root}")

    remote_base = remote_parent.replace("\\", "/").rstrip("/")
    transport = paramiko.Transport((host, int(port)))
    transport.connect(username=username, password=password)
    transport.set_keepalive(30)
    count = 0
    try:
        sftp = paramiko.SFTPClient.from_transport(transport)
        for local_file in sorted(local_root.rglob("*")):
            if not local_file.is_file():
                continue
            rel = local_file.relative_to(local_root).as_posix()
            remote_path = posixpath.join(remote_base, rel) if remote_base else rel
            remote_dir = posixpath.dirname(remote_path)
            if remote_dir:
                _ensure_remote_dir(sftp, remote_dir)
            size_mb = local_file.stat().st_size / (1024 * 1024)
            logger.info("SCP upload %s (%.1f Mo) → %s", local_file.name, size_mb, remote_path)
            with local_file.open("rb") as src:
                with sftp.file(remote_path, "wb") as dst:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
            count += 1
        logger.info("SCP terminé : %s fichier(s) vers %s", count, remote_base)
    finally:
        transport.close()
    return count


def _ensure_remote_dir(sftp, remote_dir: str) -> None:
    """Crée les répertoires parents (chemins POSIX ou Windows E:/...)."""
    normalized = remote_dir.replace("\\", "/").rstrip("/")
    if not normalized:
        return
    # Windows drive letter : E:/a/b
    if len(normalized) >= 2 and normalized[1] == ":":
        segments = normalized.split("/")
        path = segments[0]
        for part in segments[1:]:
            if not part:
                continue
            path = f"{path}/{part}"
            _mkdir_if_missing(sftp, path)
        return
    # Chemin absolu Unix
    if normalized.startswith("/"):
        path = ""
        for part in normalized.strip("/").split("/"):
            path = f"{path}/{part}"
            _mkdir_if_missing(sftp, path)
        return
    path = ""
    for part in normalized.split("/"):
        if not part:
            continue
        path = f"{path}/{part}" if path else part
        _mkdir_if_missing(sftp, path)


def _mkdir_if_missing(sftp, path: str) -> None:
    try:
        sftp.stat(path)
    except OSError:
        try:
            sftp.mkdir(path)
        except OSError:
            sftp.stat(path)
