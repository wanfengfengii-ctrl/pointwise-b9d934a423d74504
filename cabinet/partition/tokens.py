"""Opaque authorization and installation-receipt tokens for partition changes."""
from cabinet.deposit.evidence import open_evidence, seal_evidence
from cabinet.layout.catalog import CabinetError, require_identifier
from cabinet.partition.shapes import require_shape

AUTHORIZATION_KIND = 'partition_authorization'
INSTALLATION_KIND = 'partition_installation'
TOKEN_FIELDS = ('cabinet_id', 'request_id', 'target_shape')


def make_authorization(
    key: bytes, cabinet_id: str, request_id: str, target_shape: str,
) -> str:
    facts = {'cabinet_id': cabinet_id, 'request_id': request_id, 'target_shape': target_shape}
    return seal_evidence(key, AUTHORIZATION_KIND, facts)


def read_authorization(
    key: bytes, token: str,
) -> dict:
    return _read_token(key, AUTHORIZATION_KIND, token)


def make_installation_receipt(
    key: bytes, cabinet_id: str, request_id: str, target_shape: str,
) -> str:
    facts = {'cabinet_id': cabinet_id, 'request_id': request_id, 'target_shape': target_shape}
    return seal_evidence(key, INSTALLATION_KIND, facts)


def read_installation_receipt(key: bytes, token: str) -> dict:
    return _read_token(key, INSTALLATION_KIND, token)


def _read_token(key: bytes, kind: str, token) -> dict:
    if not isinstance(token, str) or not token:
        raise CabinetError(409, 'invalid_evidence')
    try:
        facts = open_evidence(key, kind, token)
        parsed = {field: require_identifier(facts.get(field), field) for field in TOKEN_FIELDS}
        parsed['target_shape'] = require_shape(facts.get('target_shape'))
    except CabinetError:
        raise
    except (ValueError, RecursionError) as error:
        raise CabinetError(409, 'invalid_evidence') from error
    return parsed
