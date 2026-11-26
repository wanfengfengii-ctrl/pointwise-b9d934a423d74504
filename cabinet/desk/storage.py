import sqlite3

from cabinet.layout.installation import initialize_layout_schema, local_transaction, open_layout_store
from cabinet.partition.storage import initialize_partition_schema


def open_desk_store(path) -> sqlite3.Connection:
    return open_layout_store(path)


def desk_transaction(path):
    return local_transaction(open_desk_store, path, write=True)


def desk_snapshot(path):
    return local_transaction(open_desk_store, path, write=False)


def initialize_desk_store(path) -> None:
    with desk_transaction(path) as connection:
        initialize_layout_schema(connection)
        connection.execute('''
            CREATE TABLE IF NOT EXISTS grants (
                grant_id TEXT PRIMARY KEY NOT NULL,
                cabinet_id TEXT NOT NULL,
                request_id TEXT UNIQUE NOT NULL,
                work_id TEXT NOT NULL,
                width TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                credential TEXT NOT NULL,
                FOREIGN KEY (cabinet_id, slot_id) REFERENCES slots(cabinet_id, slot_id)
            )
        ''')
        connection.execute('''
            CREATE INDEX IF NOT EXISTS grants_by_cabinet_slot ON grants (cabinet_id, slot_id)
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS verified_receipts (
                grant_id TEXT NOT NULL REFERENCES grants(grant_id),
                kind TEXT NOT NULL CHECK (kind IN ('deposit', 'pickup')),
                evidence TEXT NOT NULL,
                PRIMARY KEY (grant_id, kind)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS closures (
                grant_id TEXT PRIMARY KEY NOT NULL REFERENCES grants(grant_id),
                deposit_id TEXT NOT NULL,
                pickup_id TEXT NOT NULL
            )
        ''')
        initialize_partition_schema(connection, requests=True, actions=False)
