import base64
import hashlib
import hmac
import json

from cabinet.layout.catalog import CabinetError, require_identifier


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _decode(text: str) -> bytes:
    data = base64.b64decode(text + '=' * (-len(text) % 4), altchars=b'-_', validate=True)
    if _encode(data) != text:
        raise ValueError('non-canonical encoding')
    return data


def seal_evidence(key: bytes, kind: str, facts: dict) -> str:
    raw = json.dumps(
        {'kind': kind, 'facts': facts}, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode('ascii')
    signature = hmac.digest(key, raw, hashlib.sha256)
    return f'{_encode(raw)}.{_encode(signature)}'


def open_evidence(key: bytes, kind: str, token: str) -> dict:
    try:
        if not isinstance(token, str):
            raise ValueError('evidence must be a string')
        encoded, signature = token.split('.')
        raw = _decode(encoded)
        supplied = _decode(signature)
        if not hmac.compare_digest(hmac.digest(key, raw, hashlib.sha256), supplied):
            raise ValueError('evidence authentication failed')
        envelope = json.loads(raw.decode('ascii'))
        if not isinstance(envelope, dict) or envelope.get('kind') != kind:
            raise ValueError('wrong evidence purpose')
        facts = envelope.get('facts')
        if not isinstance(facts, dict):
            raise ValueError('invalid evidence facts')
    except (ValueError, RecursionError) as error:
        raise CabinetError(409, 'invalid_evidence') from error
    return facts


def evidence_identifiers(key: bytes, kind: str, token: str, fields: tuple[str, ...]) -> dict:
    facts = open_evidence(key, kind, token)
    try:
        return {field: require_identifier(facts.get(field), field) for field in fields}
    except CabinetError as error:
        raise CabinetError(409, 'invalid_evidence_binding') from error
