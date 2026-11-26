import sqlite3

from cabinet.layout.catalog import CabinetError, SlotSpec
from cabinet.layout.fit import fitting_slots
from cabinet.layout.order import order_candidates
from cabinet.partition import shapes, storage
from cabinet.settle.close import list_unclosed_slots


def choose_available_slot(connection: sqlite3.Connection, cabinet_id: str, width: int) -> SlotSpec:
    spec = storage.load_active_cabinet(connection, cabinet_id)
    if spec is None:
        raise CabinetError(409, 'cabinet_uninstalled')
    promised = list_unclosed_slots(connection, cabinet_id)
    pending = storage.pending_request(connection, cabinet_id)
    if pending is not None:
        # A pending partition freezes the whole variable zone for new issuance
        # until the kiosk installation has been confirmed back to the desk:
        # cover both the slots leaving the layout and the ones arriving.
        settings_row = storage.load_settings(connection, cabinet_id)
        frozen = set(shapes.variable_slots(pending['target_shape']))
        if settings_row is not None:
            frozen |= set(shapes.variable_slots(settings_row['current_shape']))
        promised |= frozen
    candidates = fitting_slots((slot for slot in spec.slots if slot.slot_id not in promised), width)
    ordered = order_candidates(candidates)
    if not ordered:
        raise CabinetError(409, 'no_fitting_slot')
    return ordered[0]
