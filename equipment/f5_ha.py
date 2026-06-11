"""Découverte du membre actif d'un cluster F5 BIG-IP (HA) via iControl REST."""

from __future__ import annotations

import base64
import json
import logging
import ssl
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .adapters.base import BackupAdapterError
from .f5_config import normalize_mgmt_host

if TYPE_CHECKING:
    from .models import BackupJob

logger = logging.getLogger(__name__)


def ha_peer_addresses(job: BackupJob) -> list[str]:
    """IPs de management des nœuds du cluster (administration Django)."""
    addresses: list[str] = []
    seen: set[str] = set()
    for host in job.equipment.hosts.order_by("sort_order", "pk"):
        addr = normalize_mgmt_host(host.address)
        if addr not in seen:
            seen.add(addr)
            addresses.append(addr)
    extra = job.equipment.extra if isinstance(job.equipment.extra, dict) else {}
    for raw in extra.get("ha_peers") or []:
        if not isinstance(raw, str) or not raw.strip():
            continue
        addr = normalize_mgmt_host(raw)
        if addr not in seen:
            seen.add(addr)
            addresses.append(addr)
    if not addresses:
        raise BackupAdapterError(
            "Aucun nœud de cluster F5 configuré. "
            "Ajoutez les IPs de management dans l'administration (hosts de management)."
        )
    return addresses


def _verify_tls(job: BackupJob) -> bool:
    extra = job.equipment.extra if isinstance(job.equipment.extra, dict) else {}
    if "verify_tls" in extra:
        return bool(extra["verify_tls"])
    return getattr(settings, "F5_API_VERIFY_TLS", False)


def _fetch_cm_devices(peer: str, user: str, password: str, *, verify_tls: bool) -> list[dict]:
    host = normalize_mgmt_host(peer)
    url = f"https://{host}/mgmt/tm/cm/device"
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    request = Request(
        url,
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
    try:
        with urlopen(request, timeout=60, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise BackupAdapterError(
            f"API F5 indisponible ({host}) : HTTP {exc.code} — {body}"
        ) from exc
    except URLError as exc:
        raise BackupAdapterError(f"API F5 injoignable ({host}).") from exc
    except json.JSONDecodeError as exc:
        raise BackupAdapterError(f"Réponse API F5 invalide ({host}).") from exc

    items = payload.get("items")
    if not isinstance(items, list):
        raise BackupAdapterError(f"Réponse API F5 inattendue ({host}).")
    return items


def resolve_active_mgmt_ip(
    peers: list[str],
    user: str,
    password: str,
    *,
    verify_tls: bool,
) -> str:
    """
    Interroge /mgmt/tm/cm/device et retourne managementIp du membre ``active``.
  """
    last_error: Exception | None = None
    for peer in peers:
        try:
            items = _fetch_cm_devices(peer, user, password, verify_tls=verify_tls)
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("failoverState") != "active":
                    continue
                mgmt_ip = (item.get("managementIp") or "").strip()
                if mgmt_ip:
                    active = normalize_mgmt_host(mgmt_ip)
                    logger.info(
                        "F5 HA membre actif détecté via %s : %s",
                        peer,
                        active,
                    )
                    return active
            raise BackupAdapterError(
                f"Aucun membre actif trouvé via l'API F5 ({peer})."
            )
        except BackupAdapterError as exc:
            last_error = exc
            logger.warning("F5 HA discovery via %s : %s", peer, exc)
            continue
    raise BackupAdapterError(
        "Impossible de déterminer le membre actif du cluster F5."
    ) from last_error


def resolve_active_mgmt_ip_for_job(job: BackupJob, user: str, password: str) -> str:
    peers = ha_peer_addresses(job)
    return resolve_active_mgmt_ip(peers, user, password, verify_tls=_verify_tls(job))
