from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()


class Platform(StrEnum):
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    VIDEO_CHANNEL = "video_channel"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuditTaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("platform", "rule_code", name="uq_rules_platform_rule_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[Platform] = mapped_column(
        SAEnum(Platform, name="platform_enum", native_enum=False),
        index=True,
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, name="risk_level_enum", native_enum=False),
        default=RiskLevel.MEDIUM,
        nullable=False,
    )
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    regex_patterns: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    rule_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tags: Mapped[list[RuleTag]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    embeddings: Mapped[list[RuleEmbedding]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RuleTag(Base):
    __tablename__ = "rule_tags"
    __table_args__ = (UniqueConstraint("rule_id", "tag", name="uq_rule_tags_rule_id_tag"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    tag: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    rule: Mapped[Rule] = relationship(back_populates="tags")


class RuleEmbedding(Base):
    __tablename__ = "rule_embeddings"
    __table_args__ = (UniqueConstraint("rule_id", "model_name", name="uq_rule_embeddings_rule_id_model"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.pgvector_dimension), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    rule: Mapped[Rule] = relationship(back_populates="embeddings")


class AuditTask(Base):
    __tablename__ = "audit_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_content: Mapped[str | None] = mapped_column(Text)
    requested_platforms: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[AuditTaskStatus] = mapped_column(
        SAEnum(AuditTaskStatus, name="audit_task_status_enum", native_enum=False),
        default=AuditTaskStatus.PENDING,
        nullable=False,
    )
    sentence_map: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list[AuditResult]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AuditResult(Base):
    __tablename__ = "audit_results"
    __table_args__ = (UniqueConstraint("audit_task_id", "platform", name="uq_audit_results_task_platform"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audit_tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    platform: Mapped[Platform] = mapped_column(
        SAEnum(Platform, name="platform_enum", native_enum=False),
        index=True,
        nullable=False,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, name="risk_level_enum", native_enum=False),
        nullable=False,
    )
    hit_sentences: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    matched_rules: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    rewrite_options: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    revised_text: Mapped[str] = mapped_column(Text, nullable=False)
    report: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    task: Mapped[AuditTask] = relationship(back_populates="results")
