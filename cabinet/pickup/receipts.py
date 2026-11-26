import sqlite3
from dataclasses import asdict, dataclass
from uuid import uuid4

from cabinet.deposit.evidence import evidence_identifiers, seal_evidence
from cabinet.pickup.release import ReleasedDeposit


PICKUP_FIELDS = ('cabinet_id', 'slot_id', 'grant_id', 'deposit_id', 'pickup_id')


@dataclass(frozen=True)
class PickupReceipt:
    cabinet_id: str
    slot_id: str
    grant_id: str
    deposit_id: str
    pickup_id: str
    pickup_receipt: str

    def to_json(self) -> dict:
        return asdict(self)


def make_pickup_receipt(key: bytes, released: ReleasedDeposit) -> PickupReceipt:
    facts = {**asdict(released.actual), 'pickup_id': uuid4().hex}
    return PickupReceipt(**facts, pickup_receipt=seal_evidence(key, 'pickup', facts))


def record_pickup_receipt(connection: sqlite3.Connection, receipt: PickupReceipt) -> None:
    connection.execute('''
        INSERT INTO pickup_receipts (cabinet_id, slot_id, grant_id, deposit_id, pickup_id, evidence)
        VALUES (:cabinet_id, :slot_id, :grant_id, :deposit_id, :pickup_id, :pickup_receipt)
    ''', receipt.to_json())


def find_pickup_receipt(connection: sqlite3.Connection, deposit_id: str) -> PickupReceipt | None:
    row = connection.execute('''
        SELECT cabinet_id, slot_id, grant_id, deposit_id, pickup_id, evidence AS pickup_receipt
        FROM pickup_receipts WHERE deposit_id = ?
    ''', (deposit_id,)).fetchone()
    return PickupReceipt(**dict(row)) if row is not None else None


def read_pickup_receipt(key: bytes, token: str) -> PickupReceipt:
    facts = evidence_identifiers(key, 'pickup', token, PICKUP_FIELDS)
    return PickupReceipt(**facts, pickup_receipt=token)
