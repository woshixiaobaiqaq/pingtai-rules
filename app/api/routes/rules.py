from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_rule_service
from app.schemas.common import parse_platform
from app.schemas.rule import RuleImportRequest, RuleImportResult, RuleListResponse
from app.services.rule_management import RuleManagementService

router = APIRouter()


@router.get("/rules", response_model=RuleListResponse)
def list_rules(
    platform: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: RuleManagementService = Depends(get_rule_service),
) -> RuleListResponse:
    normalized_platform = parse_platform(platform).value if platform else None
    return service.list_rules(
        platform=normalized_platform,
        tag=tag,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )


@router.post("/rules/import", response_model=RuleImportResult)
def import_rules(
    payload: RuleImportRequest,
    service: RuleManagementService = Depends(get_rule_service),
) -> RuleImportResult:
    return service.import_rules(payload.rules)

