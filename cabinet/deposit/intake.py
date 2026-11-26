from uuid import uuid4

from cabinet.deposit.check import check_delivery_grant
from cabinet.deposit.occupancy import CurrentDeposit, store_deposit
from cabinet.deposit.receipts import find_deposit_receipt, make_deposit_receipt, record_deposit_receipt
from cabinet.deposit.storage import kiosk_transaction
from cabinet.layout.catalog import CabinetError
from cabinet.pickup.tickets import issue_pickup_ticket, ticket_for_deposit


def accept_deposit(
    store_path, local_cabinet_id: str, grant_key: bytes, receipt_key: bytes, credential: str,
) -> dict:
    with kiosk_transaction(store_path) as connection:
        grant = check_delivery_grant(connection, grant_key, local_cabinet_id, credential)
        previous = find_deposit_receipt(connection, grant.grant_id)
        if previous is not None:
            if (previous.cabinet_id, previous.slot_id) != (grant.cabinet_id, grant.slot_id):
                raise CabinetError(409, 'delivery_binding_conflict')
            ticket = ticket_for_deposit(connection, previous.deposit_id)
            return {**previous.to_json(), 'pickup_ticket': ticket}

        current = CurrentDeposit(grant.cabinet_id, grant.slot_id, grant.grant_id, uuid4().hex)
        receipt = make_deposit_receipt(receipt_key, current)
        record_deposit_receipt(connection, receipt)
        store_deposit(connection, current)
        ticket = issue_pickup_ticket(connection, current)
        return {**receipt.to_json(), 'pickup_ticket': ticket}
