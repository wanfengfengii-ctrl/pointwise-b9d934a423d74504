from dataclasses import dataclass

from cabinet.desk.receipts import GrantReceipt, load_grant
from cabinet.desk.storage import desk_snapshot
from cabinet.layout.catalog import CabinetError
from cabinet.settle.close import Closure, load_closure
from cabinet.settle.reconcile import load_verified_receipts
from cabinet.settle.verify import VerifiedReceipts


@dataclass(frozen=True)
class GrantStatus:
    grant: GrantReceipt
    receipts: VerifiedReceipts
    closure: Closure | None

    def to_json(self) -> dict:
        if self.closure is not None:
            state = 'closed'
        elif self.receipts.deposit is not None or self.receipts.pickup is not None:
            state = 'pending'
        else:
            state = 'issued'
        return {
            **self.grant.to_json(),
            'status': state,
            **self.receipts.to_json(),
            'closure': self.closure.to_json() if self.closure is not None else None,
        }


def get_grant_status(store_path, key: bytes, grant_id: str) -> GrantStatus:
    with desk_snapshot(store_path) as connection:
        grant = load_grant(connection, grant_id)
        if grant is None:
            raise CabinetError(404, 'unknown_grant')
        receipts = load_verified_receipts(connection, key, grant_id)
        closure = load_closure(connection, grant_id)
    return GrantStatus(grant, receipts, closure)
