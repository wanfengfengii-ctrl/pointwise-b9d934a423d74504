from dataclasses import dataclass


class CabinetError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def require_object(value):
    if not isinstance(value, dict):
        raise CabinetError(422, 'object_required')
    return value


def require_identifier(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CabinetError(422, f'invalid_{field}')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise CabinetError(422, f'invalid_{field}') from error
    return value


def require_width(value) -> int:
    if type(value) is not int or value <= 0:
        raise CabinetError(422, 'invalid_width')
    return value


@dataclass(frozen=True)
class SlotSpec:
    slot_id: str
    width: int
    ordinal: int


@dataclass(frozen=True)
class CabinetSpec:
    cabinet_id: str
    slots: tuple[SlotSpec, ...]

    def to_json(self) -> dict:
        return {
            'cabinet_id': self.cabinet_id,
            'slots': [
                {'slot_id': slot.slot_id, 'width': slot.width}
                for slot in self.slots
            ],
        }


def parse_cabinet_spec(body: dict) -> CabinetSpec:
    cabinet_id = require_identifier(body.get('cabinet_id'), 'cabinet_id')
    raw_slots = body.get('slots')
    if not isinstance(raw_slots, list) or not raw_slots:
        raise CabinetError(422, 'invalid_slots')

    slots = []
    seen = set()
    for ordinal, raw_slot in enumerate(raw_slots):
        data = require_object(raw_slot)
        slot_id = require_identifier(data.get('slot_id'), 'slot_id')
        width = require_width(data.get('width'))
        if slot_id in seen:
            raise CabinetError(422, 'duplicate_slot')
        seen.add(slot_id)
        slots.append(SlotSpec(slot_id, width, ordinal))
    return CabinetSpec(cabinet_id, tuple(slots))
