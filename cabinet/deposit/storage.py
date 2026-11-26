import sqlite3

from cabinet.layout.catalog import CabinetError
from cabinet.layout.installation import initialize_layout_schema, local_transaction, open_layout_store


def open_kiosk_store(path) -> sqlite3.Connection:
    return open_layout_store(path)


def kiosk_transaction(path):
    return local_transaction(open_kiosk_store, path, write=True)


def initialize_kiosk_store(path, cabinet_id: str) -> None:
    with kiosk_transaction(path) as connection:
        initialize_layout_schema(connection)
        connection.execute('''
            CREATE TABLE IF NOT EXISTS kiosk_identity (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                cabinet_id TEXT NOT NULL
            )
        ''')
        connection.execute('''
            INSERT INTO kiosk_identity (singleton, cabinet_id) VALUES (1, ?)
            ON CONFLICT (singleton) DO NOTHING
        ''', (cabinet_id,))
        identity = connection.execute('SELECT cabinet_id FROM kiosk_identity WHERE singleton = 1').fetchone()
        if identity['cabinet_id'] != cabinet_id:
            raise CabinetError(409, 'kiosk_identity_conflict')

        connection.execute('''
            CREATE TABLE IF NOT EXISTS deposit_receipts (
                grant_id TEXT PRIMARY KEY NOT NULL,
                cabinet_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                deposit_id TEXT UNIQUE NOT NULL,
                evidence TEXT NOT NULL,
                FOREIGN KEY (cabinet_id, slot_id) REFERENCES slots(cabinet_id, slot_id)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS current_deposits (
                cabinet_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                grant_id TEXT UNIQUE NOT NULL REFERENCES deposit_receipts(grant_id),
                deposit_id TEXT UNIQUE NOT NULL REFERENCES deposit_receipts(deposit_id),
                PRIMARY KEY (cabinet_id, slot_id),
                FOREIGN KEY (cabinet_id, slot_id) REFERENCES slots(cabinet_id, slot_id)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS pickup_tickets (
                ticket TEXT PRIMARY KEY NOT NULL,
                cabinet_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                grant_id TEXT NOT NULL REFERENCES deposit_receipts(grant_id),
                deposit_id TEXT UNIQUE NOT NULL REFERENCES deposit_receipts(deposit_id)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS pickup_receipts (
                deposit_id TEXT PRIMARY KEY NOT NULL REFERENCES deposit_receipts(deposit_id),
                cabinet_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                grant_id TEXT NOT NULL REFERENCES deposit_receipts(grant_id),
                pickup_id TEXT UNIQUE NOT NULL,
                evidence TEXT NOT NULL
            )
        ''')
