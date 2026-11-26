import sqlite3

from cabinet.deposit.receipts import read_deposit_receipt
from cabinet.desk.storage import desk_transaction
from cabinet.layout.catalog import require_identifier
from cabinet.pickup.receipts import read_pickup_receipt
from cabinet.settle.close import close_if_complete
from cabinet.settle.verify import VerifiedReceipts, verify_receipt_submission


def load_verified_receipts(connection: sqlite3.Connection, key: bytes, grant_id: str) -> VerifiedReceipts:
    rows = connection.execute('''
        SELECT kind, evidence FROM verified_receipts WHERE grant_id = ?
    ''', (grant_id,))
    tokens = {row['kind']: row['evidence'] for row in rows}
    return VerifiedReceipts(
        deposit=read_deposit_receipt(key, tokens['deposit']) if 'deposit' in tokens else None,
        pickup=read_pickup_receipt(key, tokens['pickup']) if 'pickup' in tokens else None,
    )


def _record_new_receipts(
    connection: sqlite3.Connection, grant_id: str, before: VerifiedReceipts, after: VerifiedReceipts,
) -> None:
    for kind, token in after.to_json().items():
        if token is not None and before.to_json()[kind] is None:
            connection.execute('''
                INSERT INTO verified_receipts (grant_id, kind, evidence) VALUES (?, ?, ?)
            ''', (grant_id, kind.removesuffix('_receipt'), token))


def reconcile_receipts(store_path, key: bytes, body: dict) -> dict:
    cabinet_id = require_identifier(body.get('cabinet_id'), 'cabinet_id')
    with desk_transaction(store_path) as connection:
        grant, incoming = verify_receipt_submission(
            connection, key, cabinet_id, body.get('deposit_receipt'), body.get('pickup_receipt'),
        )
        previous = load_verified_receipts(connection, key, grant.grant_id)
        verified = previous.merged_with(incoming)
        _record_new_receipts(connection, grant.grant_id, previous, verified)
        closure = close_if_complete(connection, grant.grant_id, verified)
        return {
            'cabinet_id': grant.cabinet_id,
            'grant_id': grant.grant_id,
            'status': 'closed' if closure is not None else 'pending',
            **verified.to_json(),
            'closure': closure.to_json() if closure is not None else None,
        }
