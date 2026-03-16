from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_audit_service
from app.schemas.audit import AuditRequest, AuditResponse
from app.services.audit_orchestrator import AuditOrchestratorService

router = APIRouter()


@router.post("/audit", response_model=AuditResponse)
def audit_content(
    payload: AuditRequest,
    service: AuditOrchestratorService = Depends(get_audit_service),
) -> AuditResponse:
    return service.audit(
        content=payload.content,
        platforms=payload.platforms,
        persist=payload.persist,
    )

