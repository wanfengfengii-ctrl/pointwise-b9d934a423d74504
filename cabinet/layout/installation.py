import sqlite3
from contextlib import closing, contextmanager

from cabinet.layout.catalog import CabinetError, CabinetSpec, SlotSpec


def open_layout_store(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def local_transaction(open_store, path, *, write: bool):
    with closing(open_store(path)) as connection:
        with connection:
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection


def initialize_layout_schema(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS cabinets (
            cabinet_id TEXT PRIMARY KEY NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS slots (
            cabinet_id TEXT NOT NULL REFERENCES cabinets(cabinet_id),
            slot_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            width TEXT NOT NULL,
            PRIMARY KEY (cabinet_id, slot_id),
            UNIQUE (cabinet_id, ordinal)
        )
    ''')


def load_cabinet(connection: sqlite3.Connection, cabinet_id: str) -> CabinetSpec | None:
    rows = connection.execute('''
        SELECT slot_id, width, ordinal
        FROM slots WHERE cabinet_id = ? ORDER BY ordinal
    ''', (cabinet_id,)).fetchall()
    if not rows:
        return None
    slots = tuple(SlotSpec(row['slot_id'], int(row['width']), row['ordinal']) for row in rows)
    return CabinetSpec(cabinet_id, slots)


def install_cabinet(connection: sqlite3.Connection, proposed: CabinetSpec) -> CabinetSpec:
    existing = load_cabinet(connection, proposed.cabinet_id)
    if existing is not None:
        if existing != proposed:
            raise CabinetError(409, 'cabinet_spec_conflict')
        return existing

    connection.execute('INSERT INTO cabinets (cabinet_id) VALUES (?)', (proposed.cabinet_id,))
    connection.executemany('''
        INSERT INTO slots (cabinet_id, slot_id, ordinal, width) VALUES (?, ?, ?, ?)
    ''', ((proposed.cabinet_id, slot.slot_id, slot.ordinal, str(slot.width)) for slot in proposed.slots))
    return proposed
