import sqlite3

from cabinet.desk.receipts import GrantReceipt, read_delivery_credential
from cabinet.layout.catalog import CabinetError
from cabinet.layout.fit import fits_width
from cabinet.layout.installation import load_cabinet


def check_delivery_grant(
    connection: sqlite3.Connection, key: bytes, local_cabinet_id: str, credential: str,
) -> GrantReceipt:
    grant = read_delivery_credential(key, credential)
    if grant.cabinet_id != local_cabinet_id:
        raise CabinetError(409, 'wrong_cabinet')
    cabinet = load_cabinet(connection, local_cabinet_id)
    if cabinet is None:
        raise CabinetError(409, 'cabinet_uninstalled')
    slot = next((slot for slot in cabinet.slots if slot.slot_id == grant.slot_id), None)
    if slot is None or not fits_width(slot, grant.width):
        raise CabinetError(409, 'invalid_delivery_slot')
    return grant
