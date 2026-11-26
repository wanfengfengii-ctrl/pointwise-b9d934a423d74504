"""Desk-side partition requests: accept, finalize against receipts, look up."""
from cabinet.desk.storage import desk_snapshot, desk_transaction
from cabinet.layout.catalog import CabinetError, require_identifier
from cabinet.partition import peer, shapes, storage
from cabinet.partition.shapes import require_shape
from cabinet.partition.tokens import make_authorization, read_installation_receipt
from cabinet.settle.close import list_unclosed_slots


def _order_fields(body: dict) -> tuple[str, str, str]:
    cabinet_id = require_identifier(body.get('cabinet_id'), 'cabinet_id')
    request_id = require_identifier(body.get('request_id'), 'request_id')
    target_shape = require_shape(body.get('target_shape'))
    return cabinet_id, request_id, target_shape


def _pending_payload(row) -> dict:
    return {
        'cabinet_id': row['cabinet_id'],
        'request_id': row['request_id'],
        'target_shape': row['target_shape'],
        'status': 'pending',
        'authorization': row['authorization'],
    }


def _installed_payload(row) -> dict:
    return {
        'cabinet_id': row['cabinet_id'],
        'request_id': row['request_id'],
        'target_shape': row['target_shape'],
        'status': 'installed',
        'installation_receipt': row['installation_receipt'],
    }


def handle_partition_post(store_path, grant_key: bytes, receipt_key: bytes, body: dict) -> tuple[int, dict]:
    cabinet_id, request_id, target_shape = _order_fields(body)
    with desk_transaction(store_path) as connection:
        settings = storage.load_settings(connection, cabinet_id)
        if settings is None or not settings['partitionable']:
            raise CabinetError(409, 'partition_unavailable')

        existing = storage.find_request(connection, cabinet_id, request_id)
        if existing is not None:
            if existing['target_shape'] != target_shape:
                raise CabinetError(409, 'request_conflict')
            if existing['status'] == 'installed':
                return 200, _installed_payload(existing)
            receipt_field = body.get('installation_receipt')
            if receipt_field is None:
                return 202, _pending_payload(existing)
            return 200, _finalize(connection, receipt_key, existing, receipt_field)

        if body.get('installation_receipt') is not None:
            raise CabinetError(409, 'partition_request_unknown')
        if target_shape == settings['current_shape']:
            raise CabinetError(409, 'shape_unchanged')
        if storage.pending_request(connection, cabinet_id) is not None:
            raise CabinetError(409, 'partition_pending')
        frozen = shapes.variable_slots(settings['current_shape'])
        if list_unclosed_slots(connection, cabinet_id).intersection(frozen):
            raise CabinetError(409, 'variable_zone_busy')

        authorization = make_authorization(grant_key, cabinet_id, request_id, target_shape)
        storage.insert_request(connection, cabinet_id, request_id, target_shape, authorization)
        row = storage.find_request(connection, cabinet_id, request_id)
        return 202, _pending_payload(row)


def _finalize(connection, receipt_key: bytes, existing, receipt_field: str) -> dict:
    # The receipt must be authentic and bound to this exact cabinet/request/target.
    facts = read_installation_receipt(receipt_key, receipt_field)
    if (
        facts['cabinet_id'] != existing['cabinet_id']
        or facts['request_id'] != existing['request_id']
        or facts['target_shape'] != existing['target_shape']
    ):
        raise CabinetError(409, 'installation_receipt_conflict')
    # The two services keep separate databases: the kiosk alone confirms the
    # physical installation, so the desk verifies this receipt over loopback.
    kiosk_result = peer.verify_installation_receipt(
        existing['cabinet_id'], existing['request_id'], receipt_field,
    )
    if kiosk_result.get('target_shape') != existing['target_shape']:
        raise CabinetError(409, 'installation_receipt_conflict')
    storage.apply_shape(connection, existing['cabinet_id'], existing['target_shape'])
    storage.mark_request_installed(
        connection, existing['cabinet_id'], existing['request_id'], receipt_field,
    )
    return _installed_payload(storage.find_request(
        connection, existing['cabinet_id'], existing['request_id'],
    ))


def handle_partition_get(store_path, cabinet_id: str, request_id: str) -> tuple[int, dict]:
    with desk_snapshot(store_path) as connection:
        row = storage.find_request(connection, cabinet_id, request_id)
        if row is None:
            raise CabinetError(404, 'unknown_partition_request')
        if row['status'] == 'pending':
            return 202, _pending_payload(row)
        return 200, _installed_payload(row)
