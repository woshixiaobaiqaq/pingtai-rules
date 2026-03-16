from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Rule, RuleEmbedding, RuleTag
from app.repositories.rules import RuleRepository
from app.schemas.rule import RuleImportItem, RuleImportResult, RuleListResponse, RuleRead
from app.services.embeddings import HashEmbeddingService


class RuleManagementService:
    def __init__(
        self,
        session: Session | None,
        repository,
        embedding_service: HashEmbeddingService,
        *,
        read_only: bool = False,
    ) -> None:
        self.session = session
        self.repository = repository
        self.embedding_service = embedding_service
        self.settings = get_settings()
        self.read_only = read_only

    def list_rules(
        self,
        *,
        platform: str | None = None,
        tag: str | None = None,
        enabled: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> RuleListResponse:
        rules, total = self.repository.list_rules(
            platform=platform,
            tag=tag,
            enabled=enabled,
            limit=limit,
            offset=offset,
        )
        return RuleListResponse(
            items=[self._to_rule_read(rule) for rule in rules],
            total=total,
            limit=limit,
            offset=offset,
        )

    def import_rules(self, items: list[RuleImportItem]) -> RuleImportResult:
        if self.read_only or self.session is None or not isinstance(self.repository, RuleRepository):
            raise HTTPException(status_code=400, detail="当前为本地规则文件模式，不支持通过 API 导入规则。")

        inserted = 0
        updated = 0
        saved_rules: list[Rule] = []

        for item in items:
            rule = self.repository.get_by_platform_and_code(item.platform.value, item.rule_id)
            if rule is None:
                rule = Rule(
                    platform=item.platform,
                    rule_code=item.rule_id,
                    title=item.title,
                    content=item.content,
                    source_url=item.source_url,
                    severity=item.severity,
                    keywords=item.keywords,
                    regex_patterns=item.regex_patterns,
                    rule_metadata=item.metadata,
                    enabled=True,
                )
                self.session.add(rule)
                self.session.flush()
                inserted += 1
            else:
                rule.title = item.title
                rule.content = item.content
                rule.source_url = item.source_url
                rule.severity = item.severity
                rule.keywords = item.keywords
                rule.regex_patterns = item.regex_patterns
                rule.rule_metadata = item.metadata
                rule.tags.clear()
                rule.embeddings.clear()
                updated += 1

            rule.tags.extend([RuleTag(tag=tag.strip()) for tag in item.tags if tag.strip()])
            rule.embeddings.append(
                RuleEmbedding(
                    model_name=self.settings.embedding_model,
                    source_text=self._embedding_source_text(item),
                    embedding=self.embedding_service.embed(self._embedding_source_text(item)),
                )
            )
            saved_rules.append(rule)

        self.session.commit()
        for rule in saved_rules:
            self.session.refresh(rule)
        return RuleImportResult(
            inserted=inserted,
            updated=updated,
            items=[self._to_rule_read(rule) for rule in saved_rules],
        )

    def _embedding_source_text(self, item: RuleImportItem) -> str:
        return "\n".join(
            part
            for part in [
                item.title,
                item.content,
                " ".join(item.tags),
                " ".join(item.keywords),
            ]
            if part
        )

    def _to_rule_read(self, rule: Rule) -> RuleRead:
        return RuleRead(
            id=rule.id,
            platform=rule.platform,
            rule_id=rule.rule_code,
            title=rule.title,
            content=rule.content,
            source_url=rule.source_url,
            severity=rule.severity,
            tags=[tag.tag for tag in rule.tags],
            keywords=rule.keywords,
            regex_patterns=rule.regex_patterns,
            metadata=rule.rule_metadata,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
