import argparse
from dataclasses import dataclass
from pathlib import Path

from cabinet.deposit.intake import accept_deposit
from cabinet.deposit.storage import initialize_kiosk_store, kiosk_transaction
from cabinet.layout.catalog import CabinetError, require_identifier
from cabinet.layout.install_http import (
    CabinetHttpServer,
    CabinetJsonHandler,
    handle_install,
    serve_http,
    service_keys,
)
from cabinet.pickup.redeem import redeem_pickup


@dataclass(frozen=True)
class KioskSettings:
    store_path: Path
    cabinet_id: str
    grant_key: bytes
    receipt_key: bytes


class KioskHttpHandler(CabinetJsonHandler):
    def do_POST(self):
        self.reply(self._post)

    def _post(self) -> dict:
        settings = self.settings
        if self.route == '/cabinets':
            return handle_install(
                kiosk_transaction, settings.store_path, self.read_json(), local_cabinet_id=settings.cabinet_id,
            )
        if self.route == '/deposits':
            credential = require_identifier(self.read_json().get('credential'), 'credential')
            return accept_deposit(
                settings.store_path, settings.cabinet_id, settings.grant_key, settings.receipt_key, credential,
            )
        if self.route == '/pickups':
            ticket = require_identifier(self.read_json().get('pickup_ticket'), 'pickup_ticket')
            return redeem_pickup(settings.store_path, settings.cabinet_id, settings.receipt_key, ticket).to_json()
        raise CabinetError(404, 'unknown_route')


def create_kiosk_server(
    store_path, cabinet_id: str, grant_key: bytes, receipt_key: bytes, port: int = 0,
) -> CabinetHttpServer:
    cabinet_id = require_identifier(cabinet_id, 'cabinet_id')
    settings = KioskSettings(Path(store_path), cabinet_id, grant_key, receipt_key)
    initialize_kiosk_store(settings.store_path, cabinet_id)
    return CabinetHttpServer(KioskHttpHandler, port, settings)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description='Serve one installed art centre cabinet on loopback')
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--cabinet', required=True)
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args(argv)
    grant_key, receipt_key = service_keys(parser)
    try:
        server = create_kiosk_server(args.db, args.cabinet, grant_key, receipt_key, args.port)
    except CabinetError as error:
        parser.error(error.code)
    serve_http(server)


if __name__ == '__main__':
    main()
