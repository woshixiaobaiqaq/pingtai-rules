"""initial schema

Revision ID: 20260311_0001
Revises:
Create Date: 2026-03-11 16:15:00
"""

from __future__ import annotations

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260311_0001"
down_revision = None
branch_labels = None
depends_on = None


platform_enum = sa.Enum("douyin", "xiaohongshu", "video_channel", name="platform_enum", native_enum=False)
risk_level_enum = sa.Enum("none", "low", "medium", "high", name="risk_level_enum", native_enum=False)
audit_task_status_enum = sa.Enum(
    "pending",
    "processing",
    "completed",
    "failed",
    name="audit_task_status_enum",
    native_enum=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", platform_enum, nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("severity", risk_level_enum, nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("regex_patterns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rule_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "rule_code", name="uq_rules_platform_rule_code"),
    )
    op.create_index("ix_rules_platform", "rules", ["platform"], unique=False)

    op.create_table(
        "rule_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(length=128), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "tag", name="uq_rule_tags_rule_id_tag"),
    )
    op.create_index("ix_rule_tags_rule_id", "rule_tags", ["rule_id"], unique=False)
    op.create_index("ix_rule_tags_tag", "rule_tags", ["tag"], unique=False)

    op.create_table(
        "rule_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "model_name", name="uq_rule_embeddings_rule_id_model"),
    )
    op.create_index("ix_rule_embeddings_rule_id", "rule_embeddings", ["rule_id"], unique=False)

    op.create_table(
        "audit_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cleaned_content", sa.Text(), nullable=True),
        sa.Column("requested_platforms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", audit_task_status_enum, nullable=False),
        sa.Column("sentence_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", platform_enum, nullable=False),
        sa.Column("risk_level", risk_level_enum, nullable=False),
        sa.Column("hit_sentences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("matched_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rewrite_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revised_text", sa.Text(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["audit_task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_task_id", "platform", name="uq_audit_results_task_platform"),
    )
    op.create_index("ix_audit_results_audit_task_id", "audit_results", ["audit_task_id"], unique=False)
    op.create_index("ix_audit_results_platform", "audit_results", ["platform"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_results_platform", table_name="audit_results")
    op.drop_index("ix_audit_results_audit_task_id", table_name="audit_results")
    op.drop_table("audit_results")
    op.drop_table("audit_tasks")
    op.drop_index("ix_rule_embeddings_rule_id", table_name="rule_embeddings")
    op.drop_table("rule_embeddings")
    op.drop_index("ix_rule_tags_tag", table_name="rule_tags")
    op.drop_index("ix_rule_tags_rule_id", table_name="rule_tags")
    op.drop_table("rule_tags")
    op.drop_index("ix_rules_platform", table_name="rules")
    op.drop_table("rules")

