import sqlite3
from dataclasses import asdict, dataclass

from cabinet.layout.catalog import CabinetError


@dataclass(frozen=True)
class CurrentDeposit:
    cabinet_id: str
    slot_id: str
    grant_id: str
    deposit_id: str


def find_current_deposit(connection: sqlite3.Connection, cabinet_id: str, slot_id: str) -> CurrentDeposit | None:
    row = connection.execute('''
        SELECT cabinet_id, slot_id, grant_id, deposit_id FROM current_deposits
        WHERE cabinet_id = ? AND slot_id = ?
    ''', (cabinet_id, slot_id)).fetchone()
    return CurrentDeposit(**dict(row)) if row is not None else None


def store_deposit(connection: sqlite3.Connection, current: CurrentDeposit) -> None:
    if find_current_deposit(connection, current.cabinet_id, current.slot_id) is not None:
        raise CabinetError(409, 'slot_occupied')
    connection.execute('''
        INSERT INTO current_deposits (cabinet_id, slot_id, grant_id, deposit_id)
        VALUES (:cabinet_id, :slot_id, :grant_id, :deposit_id)
    ''', asdict(current))


def remove_matching_deposit(connection: sqlite3.Connection, expected: CurrentDeposit) -> CurrentDeposit | None:
    actual = find_current_deposit(connection, expected.cabinet_id, expected.slot_id)
    if actual != expected:
        return None
    connection.execute('''
        DELETE FROM current_deposits
        WHERE cabinet_id = :cabinet_id AND slot_id = :slot_id
          AND grant_id = :grant_id AND deposit_id = :deposit_id
    ''', asdict(actual))
    return actual
