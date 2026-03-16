from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict

from app.db.models import AuditTaskStatus, Platform, RiskLevel

PLATFORM_ALIASES = {
    "抖音": Platform.DOUYIN,
    "douyin": Platform.DOUYIN,
    "小红书": Platform.XIAOHONGSHU,
    "xiaohongshu": Platform.XIAOHONGSHU,
    "视频号": Platform.VIDEO_CHANNEL,
    "video_channel": Platform.VIDEO_CHANNEL,
    "wechat_channels": Platform.VIDEO_CHANNEL,
}


def parse_platform(value: Any) -> Platform:
    if isinstance(value, Platform):
        return value
    if value in PLATFORM_ALIASES:
        return PLATFORM_ALIASES[value]
    raise ValueError(f"Unsupported platform: {value}")


PlatformInput = Annotated[Platform, BeforeValidator(parse_platform)]


class AppBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SentenceSegment(AppBaseModel):
    sentence_id: int
    text: str
    start: int
    end: int


class CandidateTagHit(AppBaseModel):
    tag: str
    trigger_type: str
    trigger_value: str
    sentence_id: int
    sentence: str
    matched_text: str | None = None
    match_start: int | None = None
    match_end: int | None = None


class AuditTaskSummary(AppBaseModel):
    id: UUID
    status: AuditTaskStatus
    created_at: datetime | None = None
    completed_at: datetime | None = None


class RewriteOptions(AppBaseModel):
    safe: str
    balanced: str
    conversion: str


class TextHighlight(AppBaseModel):
    start: int
    end: int
    text: str
    source: str


class MatchedRule(AppBaseModel):
    rule_id: str
    title: str
    quote: str
    reason: str
    severity: RiskLevel
    similarity_score: float
    matched_keywords: list[str]
    matched_regex: list[str] = []
    matched_tags: list[str]


class SentenceRuleHit(AppBaseModel):
    sentence_id: int
    sentence: str
    start: int
    end: int
    highlights: list[TextHighlight] = []
    rules: list[MatchedRule]
