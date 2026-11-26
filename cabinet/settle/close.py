import sqlite3
from dataclasses import asdict, dataclass

from cabinet.settle.verify import VerifiedReceipts


@dataclass(frozen=True)
class Closure:
    deposit_id: str
    pickup_id: str

    def to_json(self) -> dict:
        return asdict(self)


def close_if_complete(connection: sqlite3.Connection, grant_id: str, receipts: VerifiedReceipts) -> Closure | None:
    existing = load_closure(connection, grant_id)
    if existing is not None:
        return existing
    if receipts.deposit is None or receipts.pickup is None:
        return None
    closure = Closure(receipts.deposit.deposit_id, receipts.pickup.pickup_id)
    connection.execute('''
        INSERT INTO closures (grant_id, deposit_id, pickup_id) VALUES (?, ?, ?)
    ''', (grant_id, closure.deposit_id, closure.pickup_id))
    return closure


def load_closure(connection: sqlite3.Connection, grant_id: str) -> Closure | None:
    row = connection.execute('SELECT deposit_id, pickup_id FROM closures WHERE grant_id = ?', (grant_id,)).fetchone()
    return Closure(**dict(row)) if row is not None else None


def list_unclosed_slots(connection: sqlite3.Connection, cabinet_id: str) -> set[str]:
    rows = connection.execute('''
        SELECT grant.slot_id FROM grants AS grant
        WHERE grant.cabinet_id = ? AND NOT EXISTS (
            SELECT 1 FROM closures WHERE closures.grant_id = grant.grant_id
        )
    ''', (cabinet_id,))
    return {row['slot_id'] for row in rows}
