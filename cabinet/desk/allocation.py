import sqlite3

from cabinet.layout.catalog import CabinetError, SlotSpec
from cabinet.layout.fit import fitting_slots
from cabinet.layout.installation import load_cabinet
from cabinet.layout.order import order_candidates
from cabinet.settle.close import list_unclosed_slots


def choose_available_slot(connection: sqlite3.Connection, cabinet_id: str, width: int) -> SlotSpec:
    spec = load_cabinet(connection, cabinet_id)
    if spec is None:
        raise CabinetError(409, 'cabinet_uninstalled')
    promised = list_unclosed_slots(connection, cabinet_id)
    candidates = fitting_slots((slot for slot in spec.slots if slot.slot_id not in promised), width)
    ordered = order_candidates(candidates)
    if not ordered:
        raise CabinetError(409, 'no_fitting_slot')
    return ordered[0]
