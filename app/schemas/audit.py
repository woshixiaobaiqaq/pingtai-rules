from __future__ import annotations

from pydantic import Field

from app.db.models import Platform, RiskLevel
from app.schemas.common import (
    AppBaseModel,
    AuditTaskSummary,
    CandidateTagHit,
    MatchedRule,
    PlatformInput,
    RewriteOptions,
    SentenceRuleHit,
    SentenceSegment,
)


class AuditRequest(AppBaseModel):
    content: str = Field(min_length=1)
    platforms: list[PlatformInput] | None = None
    persist: bool = True


class PlatformAuditReport(AppBaseModel):
    platform: Platform
    risk_level: RiskLevel
    candidate_tags: list[CandidateTagHit]
    hit_sentences: list[SentenceRuleHit]
    matched_rules: list[MatchedRule]
    rewrite_options: RewriteOptions
    revised_text: str


class AuditReport(AppBaseModel):
    task: AuditTaskSummary
    original_content: str
    cleaned_content: str
    sentence_segments: list[SentenceSegment]
    platform_results: list[PlatformAuditReport]


class AuditResponse(AppBaseModel):
    report: AuditReport

