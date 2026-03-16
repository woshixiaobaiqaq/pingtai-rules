from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.db.models import Platform, RiskLevel
from app.repositories.rules import RetrievedRule
from app.services.embeddings import HashEmbeddingService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class LocalRuleTag:
    tag: str


@dataclass(slots=True)
class LocalRuleEmbedding:
    model_name: str
    source_text: str
    embedding: list[float]


@dataclass(slots=True)
class LocalRule:
    id: uuid.UUID
    platform: Platform
    rule_code: str
    title: str
    content: str
    source_url: str | None
    severity: RiskLevel
    keywords: list[str]
    regex_patterns: list[str]
    rule_metadata: dict[str, object]
    enabled: bool
    tags: list[LocalRuleTag]
    embeddings: list[LocalRuleEmbedding]
    created_at: datetime
    updated_at: datetime


def _severity_score(risk_level: RiskLevel) -> int:
    return {
        RiskLevel.NONE: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
    }[risk_level]


def _resolve_path(path_like: str) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(0.0, sum(a * b for a, b in zip(left, right, strict=False)))


class LocalRuleRepository:
    def __init__(self, rules: list[LocalRule]) -> None:
        self.rules = rules

    @classmethod
    def from_manifest(
        cls,
        *,
        manifest_path: str,
        embedding_service: HashEmbeddingService,
    ) -> LocalRuleRepository:
        manifest = _resolve_path(manifest_path)
        manifest_payload = __import__("json").loads(manifest.read_text(encoding="utf-8"))
        rules: list[LocalRule] = []

        for platform_entry in manifest_payload.get("platforms", []):
            rules_file = platform_entry.get("rules_file")
            if not rules_file:
                continue
            file_path = _resolve_path(rules_file)
            if not file_path.exists():
                continue

            payload = __import__("json").loads(file_path.read_text(encoding="utf-8"))
            for raw_rule in payload.get("rules", []):
                platform = Platform(raw_rule["platform"])
                tags = [LocalRuleTag(tag=value) for value in raw_rule.get("tags", [])]
                source_text = "\n".join(
                    part
                    for part in [
                        raw_rule["title"],
                        raw_rule["content"],
                        " ".join(raw_rule.get("tags", [])),
                        " ".join(raw_rule.get("keywords", [])),
                    ]
                    if part
                )
                rules.append(
                    LocalRule(
                        id=uuid.uuid5(uuid.NAMESPACE_URL, f"{platform.value}:{raw_rule['rule_id']}"),
                        platform=platform,
                        rule_code=raw_rule["rule_id"],
                        title=raw_rule["title"],
                        content=raw_rule["content"],
                        source_url=raw_rule.get("source_url"),
                        severity=RiskLevel(raw_rule.get("severity", RiskLevel.MEDIUM)),
                        keywords=list(raw_rule.get("keywords", [])),
                        regex_patterns=list(raw_rule.get("regex_patterns", [])),
                        rule_metadata=dict(raw_rule.get("metadata", {})),
                        enabled=True,
                        tags=tags,
                        embeddings=[
                            LocalRuleEmbedding(
                                model_name=get_settings().embedding_model,
                                source_text=source_text,
                                embedding=embedding_service.embed(source_text),
                            )
                        ],
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )

        return cls(rules)

    def list_rules(
        self,
        *,
        platform: str | None = None,
        tag: str | None = None,
        enabled: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[LocalRule], int]:
        items = self.rules
        if platform:
            items = [rule for rule in items if rule.platform.value == platform]
        if enabled is not None:
            items = [rule for rule in items if rule.enabled is enabled]
        if tag:
            items = [rule for rule in items if any(rule_tag.tag == tag for rule_tag in rule.tags)]

        items = sorted(items, key=lambda rule: (_severity_score(rule.severity), rule.title), reverse=True)
        total = len(items)
        return items[offset : offset + limit], total

    def get_by_platform_and_code(self, platform: str, rule_code: str) -> LocalRule | None:
        for rule in self.rules:
            if rule.platform.value == platform and rule.rule_code == rule_code:
                return rule
        return None

    def search_by_tags(self, platform: str, tags: set[str], limit: int) -> list[RetrievedRule]:
        if not tags:
            return []

        results: list[RetrievedRule] = []
        for rule in self.rules:
            if rule.platform.value != platform or not rule.enabled:
                continue
            matched_tags = {rule_tag.tag for rule_tag in rule.tags if rule_tag.tag in tags}
            if not matched_tags:
                continue
            results.append(
                RetrievedRule(
                    rule=rule,
                    matched_tags=matched_tags,
                    recall_sources={"tag"},
                    similarity_score=0.15 * len(matched_tags),
                )
            )

        results.sort(
            key=lambda item: (_severity_score(item.rule.severity), len(item.matched_tags), item.rule.title),
            reverse=True,
        )
        return results[:limit]

    def search_by_keywords(self, platform: str, keywords: set[str], limit: int) -> list[RetrievedRule]:
        if not keywords:
            return []

        results: list[RetrievedRule] = []
        for rule in self.rules:
            if rule.platform.value != platform or not rule.enabled:
                continue
            matched_keywords = {
                keyword
                for keyword in keywords
                if keyword in rule.title or keyword in rule.content or keyword in set(rule.keywords)
            }
            if not matched_keywords:
                continue
            results.append(
                RetrievedRule(
                    rule=rule,
                    matched_keywords=matched_keywords,
                    recall_sources={"keyword"},
                    similarity_score=0.1 * len(matched_keywords),
                )
            )

        results.sort(
            key=lambda item: (_severity_score(item.rule.severity), len(item.matched_keywords), item.rule.title),
            reverse=True,
        )
        return results[:limit]

    def search_by_vector(self, platform: str, vector: list[float], limit: int) -> list[RetrievedRule]:
        if not vector:
            return []

        results: list[RetrievedRule] = []
        for rule in self.rules:
            if rule.platform.value != platform or not rule.enabled or not rule.embeddings:
                continue
            similarity = max(
                _cosine_similarity(vector, embedding.embedding)
                for embedding in rule.embeddings
            )
            results.append(
                RetrievedRule(
                    rule=rule,
                    recall_sources={"vector"},
                    similarity_score=similarity,
                )
            )

        results.sort(
            key=lambda item: (_severity_score(item.rule.severity), item.similarity_score, item.rule.title),
            reverse=True,
        )
        return results[:limit]


@lru_cache(maxsize=1)
def get_local_rule_repository() -> LocalRuleRepository:
    settings = get_settings()
    return LocalRuleRepository.from_manifest(
        manifest_path=settings.local_rule_manifest_path,
        embedding_service=HashEmbeddingService(),
    )
