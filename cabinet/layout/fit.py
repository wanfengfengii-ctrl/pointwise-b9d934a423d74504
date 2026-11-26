from collections.abc import Iterable

from cabinet.layout.catalog import SlotSpec


def fits_width(slot: SlotSpec, work_width: int) -> bool:
    return slot.width >= work_width


def fitting_slots(slots: Iterable[SlotSpec], work_width: int) -> list[SlotSpec]:
    return [slot for slot in slots if fits_width(slot, work_width)]
