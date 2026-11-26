import secrets
import sqlite3
from dataclasses import asdict, dataclass

from cabinet.deposit.occupancy import CurrentDeposit


@dataclass(frozen=True)
class PickupBinding:
    ticket: str
    cabinet_id: str
    slot_id: str
    grant_id: str
    deposit_id: str


def issue_pickup_ticket(connection: sqlite3.Connection, current: CurrentDeposit) -> str:
    binding = PickupBinding(ticket=secrets.token_urlsafe(32), **asdict(current))
    connection.execute('''
        INSERT INTO pickup_tickets (ticket, cabinet_id, slot_id, grant_id, deposit_id)
        VALUES (:ticket, :cabinet_id, :slot_id, :grant_id, :deposit_id)
    ''', asdict(binding))
    return binding.ticket


def find_pickup_binding(connection: sqlite3.Connection, ticket: str) -> PickupBinding | None:
    row = connection.execute('''
        SELECT ticket, cabinet_id, slot_id, grant_id, deposit_id FROM pickup_tickets WHERE ticket = ?
    ''', (ticket,)).fetchone()
    return PickupBinding(**dict(row)) if row is not None else None


def ticket_for_deposit(connection: sqlite3.Connection, deposit_id: str) -> str:
    row = connection.execute('SELECT ticket FROM pickup_tickets WHERE deposit_id = ?', (deposit_id,)).fetchone()
    if row is None:
        raise RuntimeError('committed deposit has no pickup ticket')
    return row['ticket']
