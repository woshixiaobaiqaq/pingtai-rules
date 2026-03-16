from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.db.models import Platform, RiskLevel
from app.schemas.common import AppBaseModel, PlatformInput


class RuleImportItem(AppBaseModel):
    platform: PlatformInput
    rule_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source_url: str | None = None
    severity: RiskLevel = RiskLevel.MEDIUM
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    regex_patterns: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class RuleImportRequest(AppBaseModel):
    rules: list[RuleImportItem]


class RuleRead(AppBaseModel):
    id: UUID
    platform: Platform
    rule_id: str
    title: str
    content: str
    source_url: str | None = None
    severity: RiskLevel
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    regex_patterns: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RuleListResponse(AppBaseModel):
    items: list[RuleRead]
    total: int
    limit: int
    offset: int


class RuleImportResult(AppBaseModel):
    inserted: int
    updated: int
    items: list[RuleRead]
