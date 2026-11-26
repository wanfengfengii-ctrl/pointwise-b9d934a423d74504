"""Kiosk-side confirmation of a physically installed partition change."""
from cabinet.deposit.storage import kiosk_transaction
from cabinet.layout.catalog import CabinetError, require_identifier
from cabinet.partition import storage
from cabinet.partition.shapes import require_shape
from cabinet.partition.tokens import make_installation_receipt, read_authorization


def handle_kiosk_partition(
    store_path, local_cabinet_id: str, grant_key: bytes, receipt_key: bytes, body: dict,
) -> tuple[int, dict]:
    cabinet_id = require_identifier(body.get('cabinet_id'), 'cabinet_id')
    request_id = require_identifier(body.get('request_id'), 'request_id')
    observed_shape = require_shape(body.get('observed_shape'))
    authorization = body.get('authorization')
    if cabinet_id != local_cabinet_id:
        raise CabinetError(409, 'wrong_cabinet')

    with kiosk_transaction(store_path) as connection:
        settings = storage.load_settings(connection, local_cabinet_id)
        if settings is None or not settings['partitionable']:
            raise CabinetError(409, 'partition_unavailable')

        previous = storage.find_action(connection, local_cabinet_id, request_id)
        if previous is not None:
            # An old confirmation only ever replays its own historical result;
            # the authorization must still belong to this cabinet and request.
            facts = read_authorization(grant_key, authorization)
            if (
                facts['cabinet_id'] != previous['cabinet_id']
                or facts['request_id'] != previous['request_id']
                or facts['target_shape'] != previous['target_shape']
            ):
                raise CabinetError(409, 'authorization_conflict')
            receipt = previous['installation_receipt']
            return 200, _installed_payload(previous, receipt)

        facts = read_authorization(grant_key, authorization)
        if (
            facts['cabinet_id'] != local_cabinet_id
            or facts['request_id'] != request_id
        ):
            raise CabinetError(409, 'authorization_conflict')
        target_shape = facts['target_shape']
        if observed_shape != target_shape:
            raise CabinetError(409, 'observed_shape_conflict')
        if settings['current_shape'] == target_shape:
            raise CabinetError(409, 'shape_unchanged')

        receipt = make_installation_receipt(receipt_key, local_cabinet_id, request_id, target_shape)
        storage.apply_shape(connection, local_cabinet_id, target_shape)
        storage.insert_action(connection, local_cabinet_id, request_id, target_shape, receipt)
        row = storage.find_action(connection, local_cabinet_id, request_id)
        return 200, _installed_payload(row, receipt)


def _installed_payload(row, receipt: str) -> dict:
    return {
        'cabinet_id': row['cabinet_id'],
        'request_id': row['request_id'],
        'target_shape': row['target_shape'],
        'status': 'installed',
        'installation_receipt': receipt,
    }


def handle_kiosk_partition_lookup(
    store_path, local_cabinet_id: str, cabinet_id: str, request_id: str,
) -> dict:
    if cabinet_id != local_cabinet_id:
        raise CabinetError(409, 'wrong_cabinet')
    with kiosk_transaction(store_path) as connection:
        row = storage.find_action(connection, local_cabinet_id, request_id)
        if row is None:
            raise CabinetError(404, 'unknown_partition_request')
        return _installed_payload(row, row['installation_receipt'])
