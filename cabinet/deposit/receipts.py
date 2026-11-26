import sqlite3
from dataclasses import asdict, dataclass

from cabinet.deposit.evidence import evidence_identifiers, seal_evidence
from cabinet.deposit.occupancy import CurrentDeposit


DEPOSIT_FIELDS = ('cabinet_id', 'slot_id', 'grant_id', 'deposit_id')


@dataclass(frozen=True)
class DepositReceipt:
    cabinet_id: str
    slot_id: str
    grant_id: str
    deposit_id: str
    deposit_receipt: str

    def to_json(self) -> dict:
        return asdict(self)


def make_deposit_receipt(key: bytes, current: CurrentDeposit) -> DepositReceipt:
    facts = asdict(current)
    return DepositReceipt(**facts, deposit_receipt=seal_evidence(key, 'deposit', facts))


def record_deposit_receipt(connection: sqlite3.Connection, receipt: DepositReceipt) -> None:
    connection.execute('''
        INSERT INTO deposit_receipts (cabinet_id, slot_id, grant_id, deposit_id, evidence)
        VALUES (:cabinet_id, :slot_id, :grant_id, :deposit_id, :deposit_receipt)
    ''', receipt.to_json())


def find_deposit_receipt(connection: sqlite3.Connection, grant_id: str) -> DepositReceipt | None:
    row = connection.execute('''
        SELECT cabinet_id, slot_id, grant_id, deposit_id, evidence AS deposit_receipt
        FROM deposit_receipts WHERE grant_id = ?
    ''', (grant_id,)).fetchone()
    return DepositReceipt(**dict(row)) if row is not None else None


def read_deposit_receipt(key: bytes, token: str) -> DepositReceipt:
    facts = evidence_identifiers(key, 'deposit', token, DEPOSIT_FIELDS)
    return DepositReceipt(**facts, deposit_receipt=token)
