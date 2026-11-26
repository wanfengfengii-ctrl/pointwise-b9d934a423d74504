from uuid import uuid4

from cabinet.desk.allocation import choose_available_slot
from cabinet.desk.intake import GrantRequest, grant_request_parameters
from cabinet.desk.receipts import (
    GrantReceipt,
    find_grant_by_request,
    make_delivery_credential,
    record_grant,
)
from cabinet.desk.storage import desk_transaction
from cabinet.layout.catalog import CabinetError


def issue_grant(store_path, key: bytes, request: GrantRequest) -> GrantReceipt:
    with desk_transaction(store_path) as connection:
        existing = find_grant_by_request(connection, request.request_id)
        if existing is not None:
            if grant_request_parameters(existing.request()) != grant_request_parameters(request):
                raise CabinetError(409, 'request_conflict')
            return existing

        slot = choose_available_slot(connection, request.cabinet_id, request.width)
        grant_id = uuid4().hex
        receipt = GrantReceipt(
            grant_id=grant_id,
            cabinet_id=request.cabinet_id,
            request_id=request.request_id,
            work_id=request.work_id,
            width=request.width,
            slot_id=slot.slot_id,
            credential=make_delivery_credential(key, grant_id, request, slot.slot_id),
        )
        record_grant(connection, receipt)
        return receipt
