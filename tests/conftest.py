from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_audit_service, get_rule_service
from app.db.models import AuditTaskStatus, Platform, RiskLevel
from app.main import create_app
from app.schemas.audit import AuditResponse, PlatformAuditReport
from app.schemas.common import AuditTaskSummary, RewriteOptions, SentenceSegment
from app.schemas.rule import RuleImportResult, RuleListResponse, RuleRead


class FakeAuditService:
    def audit(self, *, content: str, platforms, persist: bool) -> AuditResponse:
        return AuditResponse(
            report={
                "task": AuditTaskSummary(id=uuid4(), status=AuditTaskStatus.COMPLETED),
                "original_content": content,
                "cleaned_content": content.strip(),
                "sentence_segments": [
                    SentenceSegment(sentence_id=1, text=content, start=0, end=len(content))
                ],
                "platform_results": [
                    PlatformAuditReport(
                        platform=Platform.DOUYIN,
                        risk_level=RiskLevel.LOW,
                        candidate_tags=[],
                        hit_sentences=[],
                        matched_rules=[],
                        rewrite_options=RewriteOptions(
                            safe=content,
                            balanced=content,
                            conversion=content,
                        ),
                        revised_text=content,
                    )
                ],
            }
        )


class FakeRuleService:
    def list_rules(self, *, platform=None, tag=None, enabled=None, limit=20, offset=0) -> RuleListResponse:
        return RuleListResponse(
            items=[
                RuleRead(
                    id=uuid4(),
                    platform=Platform.DOUYIN,
                    rule_id="DY-001",
                    title="禁止绝对化收益承诺",
                    content="不得使用保证收益、稳赚不赔等表达。",
                    source_url=None,
                    severity=RiskLevel.HIGH,
                    tags=["financial_promise"],
                    keywords=["保证收益"],
                    regex_patterns=["\\d+天回本"],
                    metadata={},
                    enabled=True,
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
        )

    def import_rules(self, items) -> RuleImportResult:
        listed = self.list_rules(limit=len(items), offset=0)
        return RuleImportResult(inserted=len(items), updated=0, items=listed.items)


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_audit_service] = lambda: FakeAuditService()
    app.dependency_overrides[get_rule_service] = lambda: FakeRuleService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

