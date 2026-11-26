"""Desk calls back to the kiosk over loopback to verify an installation receipt."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cabinet.layout.catalog import CabinetError


def peer_base(cabinet_id: str) -> str:
    raw = os.environ.get('CABINET_PARTITION_PEERS', '')
    try:
        peers = json.loads(raw) if raw else {}
        base = peers[cabinet_id]
    except (ValueError, TypeError, KeyError) as error:
        raise CabinetError(409, 'partition_peer_unavailable') from error
    if not isinstance(base, str) or not base:
        raise CabinetError(409, 'partition_peer_unavailable')
    return base.rstrip('/')


def verify_installation_receipt(cabinet_id: str, request_id: str, receipt: str) -> dict:
    """Ask the kiosk to replay the original confirmation and return its result."""
    from urllib.parse import quote

    route = '/partitions/{}/{}'.format(
        quote(cabinet_id, safe=''), quote(request_id, safe=''),
    )
    request = Request(peer_base(cabinet_id) + route, method='GET')
    try:
        with urlopen(request, timeout=10) as response:
            status = response.code
            payload = json.load(response)
    except HTTPError as error:
        status = error.code
        try:
            payload = json.load(error)
        except ValueError:
            payload = {}
    except (URLError, OSError, ValueError, TimeoutError) as error:
        raise CabinetError(409, 'partition_peer_unavailable') from error
    if status != 200 or payload.get('installation_receipt') != receipt:
        raise CabinetError(409, 'installation_receipt_unknown')
    return payload
