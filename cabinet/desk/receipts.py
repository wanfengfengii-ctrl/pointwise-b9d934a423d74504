import sqlite3
from dataclasses import asdict, dataclass

from cabinet.deposit.evidence import open_evidence, seal_evidence
from cabinet.desk.intake import GrantRequest, parse_grant_request
from cabinet.layout.catalog import CabinetError, require_identifier


@dataclass(frozen=True)
class GrantReceipt:
    grant_id: str
    cabinet_id: str
    request_id: str
    work_id: str
    width: int
    slot_id: str
    credential: str

    def request(self) -> GrantRequest:
        return GrantRequest(self.cabinet_id, self.request_id, self.work_id, self.width)

    def to_json(self) -> dict:
        return asdict(self)


def _from_row(row: sqlite3.Row | None) -> GrantReceipt | None:
    if row is None:
        return None
    values = dict(row)
    values['width'] = int(values['width'])
    return GrantReceipt(**values)


def find_grant_by_request(connection: sqlite3.Connection, request_id: str) -> GrantReceipt | None:
    row = connection.execute('SELECT * FROM grants WHERE request_id = ?', (request_id,)).fetchone()
    return _from_row(row)


def load_grant(connection: sqlite3.Connection, grant_id: str) -> GrantReceipt | None:
    row = connection.execute('SELECT * FROM grants WHERE grant_id = ?', (grant_id,)).fetchone()
    return _from_row(row)


def record_grant(connection: sqlite3.Connection, receipt: GrantReceipt) -> None:
    values = receipt.to_json()
    values['width'] = str(receipt.width)
    connection.execute('''
        INSERT INTO grants (grant_id, cabinet_id, request_id, work_id, width, slot_id, credential)
        VALUES (:grant_id, :cabinet_id, :request_id, :work_id, :width, :slot_id, :credential)
    ''', values)


def make_delivery_credential(key: bytes, grant_id: str, request: GrantRequest, slot_id: str) -> str:
    return seal_evidence(key, 'delivery', {**asdict(request), 'grant_id': grant_id, 'slot_id': slot_id})


def read_delivery_credential(key: bytes, credential: str) -> GrantReceipt:
    data = open_evidence(key, 'delivery', credential)
    try:
        request = parse_grant_request(data)
        grant_id = require_identifier(data.get('grant_id'), 'grant_id')
        slot_id = require_identifier(data.get('slot_id'), 'slot_id')
    except CabinetError as error:
        raise CabinetError(409, 'invalid_delivery_binding') from error
    return GrantReceipt(grant_id=grant_id, slot_id=slot_id, credential=credential, **asdict(request))
