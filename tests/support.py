import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cabinet.deposit.http import create_kiosk_server
from cabinet.desk.http import create_desk_server


@dataclass(frozen=True)
class HeldRequest:
    endpoint: 'Endpoint'
    route: str
    body: bytes

    def release(self) -> tuple[int, dict]:
        return self.endpoint.request('POST', self.route, self.body)


@dataclass(frozen=True)
class HeldResponse:
    """Record the service's reply for assertions without giving it to the workflow."""

    status: int
    observed_body: dict


class Endpoint:
    def __init__(self, store_path: Path, create_server):
        self.store_path = store_path
        self.create_server = create_server
        self.server = None
        self.thread = None

    def start(self) -> None:
        if self.server is not None:
            return
        server = self.create_server(self.store_path)
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        try:
            worker.start()
        except BaseException:
            server.server_close()
            raise
        self.server = server
        self.thread = worker

    def stop(self) -> None:
        if self.server is None:
            return
        try:
            self.server.shutdown()
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError('test HTTP listener did not stop')
        finally:
            self.server.server_close()
            self.server = None
            self.thread = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def request(self, method: str, route: str, body: bytes | None = None) -> tuple[int, dict]:
        if self.server is None:
            raise RuntimeError('endpoint is stopped')
        host, port = self.server.server_address
        headers = {'Content-Type': 'application/json'} if body is not None else {}
        request = Request(f'http://{host}:{port}{route}', data=body, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.load(response)

    def get(self, route: str) -> tuple[int, dict]:
        return self.request('GET', route)

    def hold_request(self, route: str, data: dict) -> HeldRequest:
        return HeldRequest(self, route, json.dumps(data).encode('utf-8'))

    def post(self, route: str, data: dict) -> tuple[int, dict]:
        return self.hold_request(route, data).release()

    def hold_response(self, route: str, data: dict) -> HeldResponse:
        status, observed_body = self.post(route, data)
        return HeldResponse(status, observed_body)


def require_ok(result: tuple[int, dict]) -> dict:
    status, payload = result
    if status != 200:
        raise AssertionError(f'expected 200, received {status} with {payload}')
    return payload


def simultaneous(*actions):
    gate = Barrier(len(actions))

    def invoke(action):
        gate.wait(timeout=5)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(invoke, action) for action in actions]
        return [future.result(timeout=15) for future in futures]


def read_rows(endpoint: Endpoint, query: str, parameters=()) -> list[tuple]:
    uri = endpoint.store_path.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return connection.execute(query, parameters).fetchall()


class Site:
    def __init__(
        self, directory, cabinet_id='gallery', grant_key=b'test-grant-key', receipt_key=b'test-receipt-key',
    ):
        self.directory = Path(directory)
        self.cabinet_id = cabinet_id
        self.grant_key = grant_key
        self.receipt_key = receipt_key
        self.desk = Endpoint(
            self.directory / 'desk.sqlite',
            partial(create_desk_server, grant_key=grant_key, receipt_key=receipt_key),
        )
        self.kiosks = {}

    @property
    def kiosk(self) -> Endpoint:
        return self.kiosks[self.cabinet_id]

    def start(self) -> None:
        self.desk.start()
        self.add_kiosk(self.cabinet_id)

    def add_kiosk(self, cabinet_id: str) -> Endpoint:
        if cabinet_id not in self.kiosks:
            self.kiosks[cabinet_id] = Endpoint(
                self.directory / f'kiosk-{len(self.kiosks)}.sqlite',
                partial(
                    create_kiosk_server, cabinet_id=cabinet_id,
                    grant_key=self.grant_key, receipt_key=self.receipt_key,
                ),
            )
        endpoint = self.kiosks[cabinet_id]
        endpoint.start()
        return endpoint

    def stop(self) -> None:
        try:
            self.desk.stop()
        finally:
            for kiosk in self.kiosks.values():
                kiosk.stop()

    def install_body(self, *slots, cabinet_id=None) -> dict:
        return {
            'cabinet_id': cabinet_id if cabinet_id is not None else self.cabinet_id,
            'slots': [{'slot_id': slot_id, 'width': width} for slot_id, width in slots],
        }

    def install(self, *slots, cabinet_id=None) -> tuple[dict, dict]:
        body = self.install_body(*slots, cabinet_id=cabinet_id)
        kiosk = self.kiosks[body['cabinet_id']]
        return require_ok(self.desk.post('/cabinets', body)), require_ok(kiosk.post('/cabinets', body))

    def grant_body(self, request_id, width, *, work_id=None, cabinet_id=None) -> dict:
        return {
            'cabinet_id': cabinet_id if cabinet_id is not None else self.cabinet_id,
            'request_id': request_id,
            'work_id': work_id if work_id is not None else f'work-{request_id}',
            'width': width,
        }

    def issue(self, request_id, width, **fields) -> dict:
        return require_ok(self.desk.post('/grants', self.grant_body(request_id, width, **fields)))

    def deposit(self, grant: dict) -> dict:
        return require_ok(self.kiosks[grant['cabinet_id']].post('/deposits', {'credential': grant['credential']}))

    def pickup(self, deposit: dict) -> dict:
        return require_ok(self.kiosks[deposit['cabinet_id']].post('/pickups', {'pickup_ticket': deposit['pickup_ticket']}))

    def reconcile_body(self, grant: dict, deposit=None, pickup=None) -> dict:
        body = {'cabinet_id': grant['cabinet_id']}
        if deposit is not None:
            body['deposit_receipt'] = deposit['deposit_receipt']
        if pickup is not None:
            body['pickup_receipt'] = pickup['pickup_receipt']
        return body

    def reconcile(self, grant: dict, deposit=None, pickup=None) -> dict:
        return require_ok(self.desk.post('/reconcile', self.reconcile_body(grant, deposit, pickup)))

    def status(self, grant: dict) -> dict:
        return require_ok(self.desk.get('/grants/' + quote(grant['grant_id'], safe='')))

    def complete(self, grant: dict) -> tuple[dict, dict, dict]:
        deposit = self.deposit(grant)
        pickup = self.pickup(deposit)
        return deposit, pickup, self.reconcile(grant, deposit, pickup)


class CabinetCase(unittest.TestCase):
    def site_options(self) -> dict:
        return {}

    def setUp(self):
        directory = TemporaryDirectory(prefix='art-cabinet-')
        self.addCleanup(directory.cleanup)
        self.site = Site(directory.name, **self.site_options())
        self.addCleanup(self.site.stop)
        self.site.start()
