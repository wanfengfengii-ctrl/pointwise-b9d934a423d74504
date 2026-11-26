import sqlite3
from dataclasses import dataclass

from cabinet.deposit.occupancy import CurrentDeposit, remove_matching_deposit
from cabinet.layout.catalog import CabinetError
from cabinet.pickup.tickets import PickupBinding


@dataclass(frozen=True)
class ReleasedDeposit:
    actual: CurrentDeposit


def release_bound_deposit(connection: sqlite3.Connection, binding: PickupBinding) -> ReleasedDeposit:
    expected = CurrentDeposit(binding.cabinet_id, binding.slot_id, binding.grant_id, binding.deposit_id)
    actual = remove_matching_deposit(connection, expected)
    if actual is None:
        raise CabinetError(409, 'pickup_not_found')
    return ReleasedDeposit(actual)
