from collections.abc import Iterable

from cabinet.layout.catalog import SlotSpec


def order_candidates(slots: Iterable[SlotSpec]) -> list[SlotSpec]:
    return sorted(slots, key=lambda slot: (slot.width, slot.ordinal))
