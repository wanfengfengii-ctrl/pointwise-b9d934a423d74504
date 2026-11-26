"""Persistence for partitionable cabinets, shared by desk and kiosk stores."""
import json
import sqlite3

from cabinet.layout.catalog import CabinetSpec, SlotSpec
from cabinet.layout.installation import install_cabinet, load_cabinet
from cabinet.partition import shapes


def initialize_partition_schema(
    connection: sqlite3.Connection, *, requests: bool, actions: bool,
) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS partition_settings (
            cabinet_id TEXT PRIMARY KEY NOT NULL REFERENCES cabinets(cabinet_id),
            partitionable INTEGER NOT NULL CHECK (partitionable IN (0, 1)),
            current_shape TEXT NOT NULL,
            initial_spec TEXT NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS active_slots (
            cabinet_id TEXT NOT NULL REFERENCES cabinets(cabinet_id),
            slot_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            width TEXT NOT NULL,
            PRIMARY KEY (cabinet_id, slot_id)
        )
    ''')
    if requests:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS partition_requests (
                cabinet_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                target_shape TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'installed')),
                authorization TEXT NOT NULL,
                installation_receipt TEXT,
                PRIMARY KEY (cabinet_id, request_id)
            )
        ''')
    if actions:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS partition_actions (
                cabinet_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                target_shape TEXT NOT NULL,
                installation_receipt TEXT PRIMARY KEY NOT NULL
            )
        ''')


def bootstrap_partitionable(connection: sqlite3.Connection, spec: CabinetSpec) -> None:
    """Persist the initial split form of a freshly partitionable cabinet."""
    existing = connection.execute(
        'SELECT cabinet_id FROM partition_settings WHERE cabinet_id = ?', (spec.cabinet_id,),
    ).fetchone()
    if existing is not None:
        return
    payload = json.dumps(spec.to_json(), sort_keys=True, separators=(',', ':'))
    connection.execute('''
        INSERT INTO partition_settings (cabinet_id, partitionable, current_shape, initial_spec)
        VALUES (?, 1, ?, ?)
    ''', (spec.cabinet_id, shapes.SPLIT, payload))
    _replace_active_slots(connection, spec.cabinet_id, spec.slots)


def load_settings(connection: sqlite3.Connection, cabinet_id: str) -> sqlite3.Row | None:
    return connection.execute(
        'SELECT * FROM partition_settings WHERE cabinet_id = ?', (cabinet_id,),
    ).fetchone()


def load_initial_spec(connection: sqlite3.Connection, cabinet_id: str) -> CabinetSpec | None:
    row = load_settings(connection, cabinet_id)
    if row is None:
        return None
    payload = json.loads(row['initial_spec'])
    slots = tuple(
        SlotSpec(slot['slot_id'], slot['width'], ordinal)
        for ordinal, slot in enumerate(payload['slots'])
    )
    return CabinetSpec(payload['cabinet_id'], slots)


def current_shape(connection: sqlite3.Connection, cabinet_id: str) -> str | None:
    row = load_settings(connection, cabinet_id)
    return row['current_shape'] if row is not None else None


def load_active_cabinet(connection: sqlite3.Connection, cabinet_id: str) -> CabinetSpec | None:
    if load_settings(connection, cabinet_id) is not None:
        rows = connection.execute('''
            SELECT slot_id, width, ordinal FROM active_slots
            WHERE cabinet_id = ? ORDER BY ordinal
        ''', (cabinet_id,)).fetchall()
        if not rows:
            return None
        slots = tuple(SlotSpec(row['slot_id'], int(row['width']), row['ordinal']) for row in rows)
        return CabinetSpec(cabinet_id, slots)
    return load_cabinet(connection, cabinet_id)


def _replace_active_slots(connection: sqlite3.Connection, cabinet_id: str, slots) -> None:
    connection.execute('DELETE FROM active_slots WHERE cabinet_id = ?', (cabinet_id,))
    connection.executemany('''
        INSERT INTO active_slots (cabinet_id, slot_id, ordinal, width) VALUES (?, ?, ?, ?)
    ''', ((cabinet_id, slot.slot_id, slot.ordinal, str(slot.width)) for slot in slots))


def apply_shape(connection: sqlite3.Connection, cabinet_id: str, shape: str) -> None:
    """Move the active layout to ``shape`` and keep every historic slot on record."""
    spec = load_initial_spec(connection, cabinet_id)
    active = shapes.shape_slots(spec, shape)
    known = {
        row['slot_id']
        for row in connection.execute(
            'SELECT slot_id FROM slots WHERE cabinet_id = ?', (cabinet_id,),
        ).fetchall()
    }
    for slot in active:
        if slot.slot_id not in known:
            ordinal_row = connection.execute(
                'SELECT COALESCE(MAX(ordinal) + 1, 0) AS next_ordinal FROM slots WHERE cabinet_id = ?',
                (cabinet_id,),
            ).fetchone()
            connection.execute('''
                INSERT INTO slots (cabinet_id, slot_id, ordinal, width) VALUES (?, ?, ?, ?)
            ''', (cabinet_id, slot.slot_id, ordinal_row['next_ordinal'], str(slot.width)))
            known.add(slot.slot_id)
    _replace_active_slots(connection, cabinet_id, active)
    connection.execute(
        'UPDATE partition_settings SET current_shape = ? WHERE cabinet_id = ?',
        (shape, cabinet_id),
    )


def find_request(connection: sqlite3.Connection, cabinet_id: str, request_id: str) -> sqlite3.Row | None:
    return connection.execute('''
        SELECT * FROM partition_requests WHERE cabinet_id = ? AND request_id = ?
    ''', (cabinet_id, request_id)).fetchone()


def pending_request(connection: sqlite3.Connection, cabinet_id: str) -> sqlite3.Row | None:
    return connection.execute('''
        SELECT * FROM partition_requests WHERE cabinet_id = ? AND status = 'pending'
    ''', (cabinet_id,)).fetchone()


def insert_request(
    connection: sqlite3.Connection, cabinet_id: str, request_id: str,
    target_shape: str, authorization: str,
) -> None:
    connection.execute('''
        INSERT INTO partition_requests
            (cabinet_id, request_id, target_shape, status, authorization, installation_receipt)
        VALUES (?, ?, ?, 'pending', ?, NULL)
    ''', (cabinet_id, request_id, target_shape, authorization))


def mark_request_installed(
    connection: sqlite3.Connection, cabinet_id: str, request_id: str, installation_receipt: str,
) -> None:
    connection.execute('''
        UPDATE partition_requests
        SET status = 'installed', installation_receipt = ?
        WHERE cabinet_id = ? AND request_id = ?
    ''', (installation_receipt, cabinet_id, request_id))


def find_action(connection: sqlite3.Connection, cabinet_id: str, request_id: str) -> sqlite3.Row | None:
    return connection.execute('''
        SELECT * FROM partition_actions WHERE cabinet_id = ? AND request_id = ?
    ''', (cabinet_id, request_id)).fetchone()


def find_action_by_receipt(connection: sqlite3.Connection, installation_receipt: str) -> sqlite3.Row | None:
    return connection.execute('''
        SELECT * FROM partition_actions WHERE installation_receipt = ?
    ''', (installation_receipt,)).fetchone()


def insert_action(
    connection: sqlite3.Connection, cabinet_id: str, request_id: str,
    target_shape: str, installation_receipt: str,
) -> None:
    connection.execute('''
        INSERT INTO partition_actions (cabinet_id, request_id, target_shape, installation_receipt)
        VALUES (?, ?, ?, ?)
    ''', (cabinet_id, request_id, target_shape, installation_receipt))


def install_with_partition_flag(
    connection: sqlite3.Connection, spec: CabinetSpec, partitionable: bool,
) -> dict:
    """Install shared by desk/kiosk: preserve replay and remember the flag."""
    settings = load_settings(connection, spec.cabinet_id)
    if settings is not None:
        initial = load_initial_spec(connection, spec.cabinet_id)
        if initial != spec or bool(settings['partitionable']) != partitionable:
            from cabinet.layout.catalog import CabinetError
            raise CabinetError(409, 'cabinet_spec_conflict')
        return {**spec.to_json(), 'partitionable': partitionable}
    install_cabinet(connection, spec)
    if partitionable:
        bootstrap_partitionable(connection, spec)
        return {**spec.to_json(), 'partitionable': True}
    return spec.to_json()
