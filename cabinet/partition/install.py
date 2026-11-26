"""Installation entry point that also records the partitionable flag."""
from cabinet.layout.catalog import CabinetError, parse_cabinet_spec
from cabinet.partition import storage


def _require_partitionable(body: dict) -> bool:
    value = body.get('partitionable', False)
    if not isinstance(value, bool):
        raise CabinetError(422, 'invalid_partitionable')
    return value


def handle_partitionable_install(transaction, store_path, body: dict, *, local_cabinet_id=None) -> dict:
    spec = parse_cabinet_spec(body)
    if local_cabinet_id is not None and spec.cabinet_id != local_cabinet_id:
        raise CabinetError(409, 'wrong_cabinet')
    partitionable = _require_partitionable(body)
    with transaction(store_path) as connection:
        return storage.install_with_partition_flag(connection, spec, partitionable)
