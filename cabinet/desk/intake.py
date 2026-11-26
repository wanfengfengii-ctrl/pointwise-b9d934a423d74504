from dataclasses import dataclass

from cabinet.layout.catalog import require_identifier, require_width


@dataclass(frozen=True)
class GrantRequest:
    cabinet_id: str
    request_id: str
    work_id: str
    width: int


def parse_grant_request(body: dict) -> GrantRequest:
    return GrantRequest(
        cabinet_id=require_identifier(body.get('cabinet_id'), 'cabinet_id'),
        request_id=require_identifier(body.get('request_id'), 'request_id'),
        work_id=require_identifier(body.get('work_id'), 'work_id'),
        width=require_width(body.get('width')),
    )


def grant_request_parameters(request: GrantRequest) -> tuple[str, str, int]:
    return request.cabinet_id, request.work_id, request.width
