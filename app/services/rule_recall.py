from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.db.models import Platform, RiskLevel, Rule
from app.repositories.rules import RetrievedRule, RuleRepository
from app.schemas.common import CandidateTagHit
from app.services.embeddings import HashEmbeddingService


@dataclass(slots=True)
class RecallCandidate:
    rule: Rule
    matched_tags: set[str] = field(default_factory=set)
    matched_keywords: set[str] = field(default_factory=set)
    similarity_score: float = 0.0
    recall_sources: set[str] = field(default_factory=set)


class RuleRecallService:
    def __init__(
        self,
        repository: RuleRepository,
        embedding_service: HashEmbeddingService,
    ) -> None:
        self.repository = repository
        self.embedding_service = embedding_service
        self.settings = get_settings()

    def recall(
        self,
        *,
        platform: Platform,
        content: str,
        candidate_hits: list[CandidateTagHit],
    ) -> list[RecallCandidate]:
        tags = {hit.tag for hit in candidate_hits}
        keywords = {
            hit.trigger_value
            for hit in candidate_hits
            if hit.trigger_type in {"keyword", "fuzzy_keyword"}
        }
        query_vector = self.embedding_service.embed(content)

        merged: dict[str, RecallCandidate] = {}
        for batch in (
            self.repository.search_by_tags(platform.value, tags, self.settings.default_rule_limit),
            self.repository.search_by_keywords(platform.value, keywords, self.settings.default_rule_limit),
            self.repository.search_by_vector(platform.value, query_vector, self.settings.default_vector_limit),
        ):
            self._merge_candidates(merged, batch)

        candidates = list(merged.values())
        candidates.sort(
            key=lambda item: (
                self._severity_score(item.rule.severity),
                len(item.matched_tags),
                len(item.matched_keywords),
                item.similarity_score,
            ),
            reverse=True,
        )
        return candidates

    def _merge_candidates(
        self,
        merged: dict[str, RecallCandidate],
        batch: list[RetrievedRule],
    ) -> None:
        for item in batch:
            key = str(item.rule.id)
            if key not in merged:
                merged[key] = RecallCandidate(rule=item.rule)
            target = merged[key]
            target.matched_tags.update(item.matched_tags)
            target.matched_keywords.update(item.matched_keywords)
            target.recall_sources.update(item.recall_sources)
            target.similarity_score = max(target.similarity_score, item.similarity_score)

    def _severity_score(self, risk_level: RiskLevel) -> int:
        return {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }[risk_level]
