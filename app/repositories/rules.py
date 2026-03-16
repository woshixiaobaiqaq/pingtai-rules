from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Rule, RuleEmbedding, RuleTag


@dataclass(slots=True)
class RetrievedRule:
    rule: Rule
    matched_tags: set[str] = field(default_factory=set)
    matched_keywords: set[str] = field(default_factory=set)
    similarity_score: float = 0.0
    recall_sources: set[str] = field(default_factory=set)


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_rules(
        self,
        *,
        platform: str | None = None,
        tag: str | None = None,
        enabled: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Rule], int]:
        base = select(Rule).options(selectinload(Rule.tags), selectinload(Rule.embeddings))
        if platform:
            base = base.where(Rule.platform == platform)
        if enabled is not None:
            base = base.where(Rule.enabled.is_(enabled))
        if tag:
            base = base.join(Rule.tags).where(RuleTag.tag == tag)

        count_query = select(func.count()).select_from(base.distinct().subquery())
        total = self.session.scalar(count_query) or 0

        items = (
            self.session.scalars(base.order_by(Rule.created_at.desc()).offset(offset).limit(limit))
            .unique()
            .all()
        )
        return items, total

    def get_by_platform_and_code(self, platform: str, rule_code: str) -> Rule | None:
        query = (
            select(Rule)
            .options(selectinload(Rule.tags), selectinload(Rule.embeddings))
            .where(Rule.platform == platform, Rule.rule_code == rule_code)
        )
        return self.session.scalar(query)

    def search_by_tags(self, platform: str, tags: set[str], limit: int) -> list[RetrievedRule]:
        if not tags:
            return []

        query = (
            select(Rule)
            .join(Rule.tags)
            .options(selectinload(Rule.tags), selectinload(Rule.embeddings))
            .where(Rule.platform == platform, Rule.enabled.is_(True), RuleTag.tag.in_(sorted(tags)))
            .limit(limit)
        )
        results: list[RetrievedRule] = []
        for rule in self.session.scalars(query).unique().all():
            matched_tags = {rule_tag.tag for rule_tag in rule.tags if rule_tag.tag in tags}
            results.append(
                RetrievedRule(
                    rule=rule,
                    matched_tags=matched_tags,
                    recall_sources={"tag"},
                    similarity_score=0.15 * len(matched_tags),
                )
            )
        return results

    def search_by_keywords(self, platform: str, keywords: set[str], limit: int) -> list[RetrievedRule]:
        if not keywords:
            return []

        clauses = []
        for keyword in sorted(keywords):
            like_clause = f"%{keyword}%"
            clauses.append(
                or_(
                    Rule.title.ilike(like_clause),
                    Rule.content.ilike(like_clause),
                    cast(Rule.keywords, Text).ilike(like_clause),
                )
            )

        query = (
            select(Rule)
            .options(selectinload(Rule.tags), selectinload(Rule.embeddings))
            .where(Rule.platform == platform, Rule.enabled.is_(True), or_(*clauses))
            .limit(limit)
        )
        results: list[RetrievedRule] = []
        for rule in self.session.scalars(query).unique().all():
            matched_keywords = {keyword for keyword in keywords if keyword in rule.content or keyword in rule.title}
            matched_keywords.update({keyword for keyword in keywords if keyword in set(rule.keywords)})
            results.append(
                RetrievedRule(
                    rule=rule,
                    matched_keywords=matched_keywords,
                    recall_sources={"keyword"},
                    similarity_score=0.1 * len(matched_keywords),
                )
            )
        return results

    def search_by_vector(self, platform: str, vector: list[float], limit: int) -> list[RetrievedRule]:
        if not vector:
            return []

        distance = RuleEmbedding.embedding.cosine_distance(vector)
        query = (
            select(Rule, distance.label("distance"))
            .join(Rule.embeddings)
            .options(selectinload(Rule.tags), selectinload(Rule.embeddings))
            .where(Rule.platform == platform, Rule.enabled.is_(True))
            .order_by(distance.asc())
            .limit(limit)
        )
        results: list[RetrievedRule] = []
        for rule, raw_distance in self.session.execute(query).all():
            similarity = max(0.0, 1.0 - float(raw_distance or 1.0))
            results.append(
                RetrievedRule(
                    rule=rule,
                    recall_sources={"vector"},
                    similarity_score=similarity,
                )
            )
        return results

