from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import database_available, get_db_session
from app.repositories.rules import RuleRepository
from app.services.audit_orchestrator import AuditOrchestratorService
from app.services.embeddings import HashEmbeddingService
from app.services.local_rule_source import get_local_rule_repository
from app.services.rule_management import RuleManagementService


def use_local_rule_source() -> bool:
    settings = get_settings()
    if settings.rule_source_mode == "file":
        return True
    if settings.rule_source_mode == "database":
        return False
    return not database_available()


def get_runtime_db_session(db: Session = Depends(get_db_session)) -> Session | None:
    if use_local_rule_source():
        return None
    return db


def get_audit_service(db: Session | None = Depends(get_runtime_db_session)) -> AuditOrchestratorService:
    if use_local_rule_source():
        return AuditOrchestratorService(db, get_local_rule_repository())
    assert db is not None
    return AuditOrchestratorService(db, RuleRepository(db))


def get_rule_service(db: Session | None = Depends(get_runtime_db_session)) -> RuleManagementService:
    if use_local_rule_source():
        return RuleManagementService(
            session=None,
            repository=get_local_rule_repository(),
            embedding_service=HashEmbeddingService(),
            read_only=True,
        )
    assert db is not None
    return RuleManagementService(
        session=db,
        repository=RuleRepository(db),
        embedding_service=HashEmbeddingService(),
    )
