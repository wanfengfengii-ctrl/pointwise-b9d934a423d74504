import sqlite3
from dataclasses import dataclass

from cabinet.deposit.receipts import DepositReceipt, read_deposit_receipt
from cabinet.desk.receipts import GrantReceipt, load_grant
from cabinet.layout.catalog import CabinetError
from cabinet.pickup.receipts import PickupReceipt, read_pickup_receipt


@dataclass(frozen=True)
class VerifiedReceipts:
    deposit: DepositReceipt | None = None
    pickup: PickupReceipt | None = None

    def merged_with(self, incoming: 'VerifiedReceipts') -> 'VerifiedReceipts':
        for previous, new in ((self.deposit, incoming.deposit), (self.pickup, incoming.pickup)):
            if previous is not None and new is not None and previous != new:
                raise CabinetError(409, 'receipt_conflict')
        merged = VerifiedReceipts(self.deposit or incoming.deposit, self.pickup or incoming.pickup)
        require_matching_receipts(merged.deposit, merged.pickup)
        return merged

    def to_json(self) -> dict:
        return {
            'deposit_receipt': self.deposit.deposit_receipt if self.deposit is not None else None,
            'pickup_receipt': self.pickup.pickup_receipt if self.pickup is not None else None,
        }


def _grant_binding(receipt) -> tuple[str, str, str]:
    return receipt.cabinet_id, receipt.slot_id, receipt.grant_id


def require_matching_receipts(deposit: DepositReceipt | None, pickup: PickupReceipt | None) -> None:
    if deposit is None or pickup is None:
        return
    if _grant_binding(deposit) != _grant_binding(pickup) or deposit.deposit_id != pickup.deposit_id:
        raise CabinetError(409, 'receipt_pair_conflict')


def verify_receipt_submission(
    connection: sqlite3.Connection, key: bytes, cabinet_id: str,
    deposit_token: str | None, pickup_token: str | None,
) -> tuple[GrantReceipt, VerifiedReceipts]:
    if deposit_token is None and pickup_token is None:
        raise CabinetError(422, 'receipt_required')
    deposit = read_deposit_receipt(key, deposit_token) if deposit_token is not None else None
    pickup = read_pickup_receipt(key, pickup_token) if pickup_token is not None else None
    require_matching_receipts(deposit, pickup)
    reference = deposit or pickup
    if reference.cabinet_id != cabinet_id:
        raise CabinetError(409, 'wrong_cabinet')
    grant = load_grant(connection, reference.grant_id)
    if grant is None or _grant_binding(grant) != _grant_binding(reference):
        raise CabinetError(409, 'receipt_grant_conflict')
    return grant, VerifiedReceipts(deposit, pickup)
