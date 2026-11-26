import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from cabinet.desk.intake import parse_grant_request
from cabinet.desk.issue import issue_grant
from cabinet.desk.storage import desk_transaction, initialize_desk_store
from cabinet.layout.catalog import CabinetError
from cabinet.layout.install_http import (
    CabinetHttpServer,
    CabinetJsonHandler,
    handle_install,
    serve_http,
    service_keys,
)
from cabinet.settle.reconcile import reconcile_receipts
from cabinet.settle.status import get_grant_status


@dataclass(frozen=True)
class DeskSettings:
    store_path: Path
    grant_key: bytes
    receipt_key: bytes


class DeskHttpHandler(CabinetJsonHandler):
    def do_POST(self):
        self.reply(self._post)

    def _post(self) -> dict:
        settings = self.settings
        if self.route == '/cabinets':
            return handle_install(desk_transaction, settings.store_path, self.read_json())
        if self.route == '/grants':
            request = parse_grant_request(self.read_json())
            return issue_grant(settings.store_path, settings.grant_key, request).to_json()
        if self.route == '/reconcile':
            return reconcile_receipts(settings.store_path, settings.receipt_key, self.read_json())
        raise CabinetError(404, 'unknown_route')

    def do_GET(self):
        self.reply(self._get)

    def _get(self) -> dict:
        prefix = '/grants/'
        if not self.route.startswith(prefix):
            raise CabinetError(404, 'unknown_route')
        grant_id = unquote(self.route[len(prefix):])
        if not grant_id or '/' in grant_id:
            raise CabinetError(404, 'unknown_grant')
        settings = self.settings
        return get_grant_status(settings.store_path, settings.receipt_key, grant_id).to_json()


def create_desk_server(store_path, grant_key: bytes, receipt_key: bytes, port: int = 0) -> CabinetHttpServer:
    settings = DeskSettings(Path(store_path), grant_key, receipt_key)
    initialize_desk_store(settings.store_path)
    return CabinetHttpServer(DeskHttpHandler, port, settings)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description='Serve the art centre desk on loopback')
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args(argv)
    grant_key, receipt_key = service_keys(parser)
    serve_http(create_desk_server(args.db, grant_key, receipt_key, args.port))


if __name__ == '__main__':
    main()
