"""Shape vocabulary for cabinets whose L/R divider can be swapped."""
from cabinet.layout.catalog import CabinetError, CabinetSpec, SlotSpec

SPLIT = 'split'
MERGED = 'merged'
SHAPES = (SPLIT, MERGED)

FIXED_SLOT = 'F'
LEFT_SLOT = 'L'
RIGHT_SLOT = 'R'
MERGED_SLOT = 'M'

VARIABLE_SLOTS = {
    SPLIT: (LEFT_SLOT, RIGHT_SLOT),
    MERGED: (MERGED_SLOT,),
}


def require_shape(value) -> str:
    if value not in SHAPES:
        raise CabinetError(422, 'invalid_target_shape')
    return value


def shape_slots(spec: CabinetSpec, shape: str):
    """Return the active slots of an initial split-form spec under a shape."""
    by_id = {slot.slot_id: slot for slot in spec.slots}
    fixed = by_id[FIXED_SLOT]
    if shape == SPLIT:
        return tuple(sorted(
            (by_id[FIXED_SLOT], by_id[LEFT_SLOT], by_id[RIGHT_SLOT]),
            key=lambda slot: slot.ordinal,
        ))
    merged_width = by_id[LEFT_SLOT].width + by_id[RIGHT_SLOT].width
    merged = SlotSpec(MERGED_SLOT, merged_width, 1)
    return (fixed, merged)


def variable_slots(shape: str) -> tuple[str, ...]:
    return VARIABLE_SLOTS[shape]
