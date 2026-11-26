import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cabinet.layout.catalog import CabinetError, parse_cabinet_spec, require_object
from cabinet.layout.installation import install_cabinet


MAX_BODY_BYTES = 1_048_576


def _reject_nonfinite(_value):
    raise ValueError('non-finite JSON number')


class CabinetJsonHandler(BaseHTTPRequestHandler):
    @property
    def settings(self):
        return self.server.settings

    @property
    def route(self) -> str:
        return self.path.partition('?')[0]

    def read_json(self) -> dict:
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or self.headers.get('Transfer-Encoding') is not None:
            raise CabinetError(422, 'invalid_content_length')
        try:
            length = int(lengths[0])
        except ValueError as error:
            raise CabinetError(422, 'invalid_content_length') from error
        if not 0 < length <= MAX_BODY_BYTES:
            raise CabinetError(422, 'invalid_content_length')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise CabinetError(422, 'incomplete_body')
        try:
            body = json.loads(raw.decode('utf-8'), parse_constant=_reject_nonfinite)
        except (ValueError, RecursionError) as error:
            raise CabinetError(422, 'invalid_json') from error
        return require_object(body)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def reply(self, action) -> None:
        try:
            outcome = action()
            if isinstance(outcome, tuple):
                status, payload = outcome
            else:
                status, payload = 200, outcome
        except CabinetError as error:
            status, payload = error.status, {'error': error.code}
        try:
            self.send_json(status, payload)
        except (BrokenPipeError, ConnectionResetError):
            # The client can recover a committed result by replaying its request.
            return

    def log_message(self, _format, *args):
        return


def handle_install(transaction, store_path, body: dict, *, local_cabinet_id=None) -> dict:
    spec = parse_cabinet_spec(body)
    if local_cabinet_id is not None and spec.cabinet_id != local_cabinet_id:
        raise CabinetError(409, 'wrong_cabinet')
    with transaction(store_path) as connection:
        result = install_cabinet(connection, spec)
    return result.to_json()


class CabinetHttpServer(ThreadingHTTPServer):
    def __init__(self, handler, port: int, settings):
        self.settings = settings
        super().__init__(('127.0.0.1', port), handler)


def service_keys(parser) -> tuple[bytes, bytes]:
    names = ('CABINET_GRANT_KEY', 'CABINET_RECEIPT_KEY')
    values = tuple(os.environ.get(name, '') for name in names)
    for name, value in zip(names, values):
        if not value:
            parser.error(f'{name} must be set')
    return values[0].encode('utf-8'), values[1].encode('utf-8')


def serve_http(server: CabinetHttpServer) -> None:
    with server:
        host, port = server.server_address
        print(json.dumps({'host': host, 'port': port}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return
