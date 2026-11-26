from cabinet.deposit.storage import kiosk_transaction
from cabinet.layout.catalog import CabinetError
from cabinet.pickup.receipts import find_pickup_receipt, make_pickup_receipt, record_pickup_receipt
from cabinet.pickup.release import release_bound_deposit
from cabinet.pickup.tickets import find_pickup_binding


def redeem_pickup(store_path, local_cabinet_id: str, receipt_key: bytes, ticket: str):
    with kiosk_transaction(store_path) as connection:
        binding = find_pickup_binding(connection, ticket)
        if binding is None:
            raise CabinetError(409, 'pickup_not_found')
        if binding.cabinet_id != local_cabinet_id:
            raise CabinetError(409, 'wrong_cabinet')
        previous = find_pickup_receipt(connection, binding.deposit_id)
        if previous is not None:
            return previous

        released = release_bound_deposit(connection, binding)
        receipt = make_pickup_receipt(receipt_key, released)
        record_pickup_receipt(connection, receipt)
        return receipt
