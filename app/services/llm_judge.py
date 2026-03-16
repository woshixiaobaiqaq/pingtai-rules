from __future__ import annotations

import re
from collections import defaultdict

from app.db.models import Platform, RiskLevel
from app.schemas.common import (
    CandidateTagHit,
    MatchedRule,
    SentenceRuleHit,
    SentenceSegment,
    TextHighlight,
)
from app.services.fuzzy_matching import FuzzyMatchResult, find_fuzzy_match, text_similarity
from app.services.rule_recall import RecallCandidate


class RuleBoundJudgeService:
    """
    A deterministic, rule-grounded judge that only emits findings from recalled rules.

    The service exposes `build_prompt` for future external LLM integration, but the
    default runtime path keeps judgment fully bounded by candidate rules.
    """

    def build_prompt(
        self,
        *,
        platform: Platform,
        content: str,
        candidate_rules: list[RecallCandidate],
    ) -> str:
        lines = [
            f"Platform: {platform.value}",
            "You may only judge with the following candidate rules.",
            "Do not invent any new rules.",
            "",
            "Candidate rules:",
        ]
        for item in candidate_rules:
            lines.append(f"- {item.rule.rule_code}: {item.rule.title}")
            lines.append(f"  Quote: {item.rule.content}")
            if item.rule.keywords:
                lines.append(f"  Keywords: {', '.join(item.rule.keywords)}")
            if item.rule.regex_patterns:
                lines.append(f"  Regex: {', '.join(item.rule.regex_patterns)}")
        lines.extend(["", "Content:", content])
        return "\n".join(lines)

    def judge(
        self,
        *,
        platform: Platform,
        sentences: list[SentenceSegment],
        candidate_hits: list[CandidateTagHit],
        recalled_rules: list[RecallCandidate],
    ) -> tuple[RiskLevel, list[SentenceRuleHit], list[MatchedRule]]:
        hits_by_sentence: dict[int, list[MatchedRule]] = defaultdict(list)
        tags_by_sentence: dict[int, set[str]] = defaultdict(set)
        candidate_hits_by_sentence: dict[int, list[CandidateTagHit]] = defaultdict(list)
        for tag_hit in candidate_hits:
            tags_by_sentence[tag_hit.sentence_id].add(tag_hit.tag)
            candidate_hits_by_sentence[tag_hit.sentence_id].append(tag_hit)

        for candidate in recalled_rules:
            rule = candidate.rule
            rule_tag_names = {tag.tag for tag in rule.tags}
            compiled_patterns = []
            for pattern in rule.regex_patterns:
                try:
                    compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
                except re.error:
                    continue

            for sentence in sentences:
                matched_keywords = [keyword for keyword in rule.keywords if keyword.lower() in sentence.text.lower()]
                matched_regex = [pattern.pattern for pattern in compiled_patterns if pattern.search(sentence.text)]
                matched_tags = sorted(tags_by_sentence[sentence.sentence_id].intersection(rule_tag_names))
                fuzzy_matches = self._collect_fuzzy_matches(
                    sentence.text,
                    rule.keywords,
                    matched_keywords,
                )
                semantic_support = self._semantic_support_score(sentence.text, rule.title, rule.content, rule.keywords)

                if not matched_keywords and not matched_regex and not fuzzy_matches and not matched_tags:
                    continue
                if (
                    not matched_keywords
                    and not matched_regex
                    and not fuzzy_matches
                    and matched_tags
                    and semantic_support < 0.38
                ):
                    continue

                reason_parts = []
                if matched_tags:
                    reason_parts.append(f"命中标签: {', '.join(matched_tags)}")
                if matched_keywords:
                    reason_parts.append(f"命中关键词: {', '.join(matched_keywords)}")
                if fuzzy_matches:
                    fuzzy_details = ", ".join(
                        f"{match.query}≈{match.matched_text}({match.score:.2f})" for match in fuzzy_matches
                    )
                    reason_parts.append(f"模糊命中: {fuzzy_details}")
                if matched_regex:
                    reason_parts.append(f"命中正则: {', '.join(matched_regex)}")
                if not matched_keywords and not matched_regex and matched_tags:
                    reason_parts.append(f"语义支持分: {semantic_support:.2f}")

                matched_rule = MatchedRule(
                    rule_id=rule.rule_code,
                    title=rule.title,
                    quote=rule.content,
                    reason="；".join(reason_parts),
                    severity=rule.severity,
                    similarity_score=round(candidate.similarity_score, 4),
                    matched_keywords=self._dedupe_values(
                        [*matched_keywords, *[match.matched_text for match in fuzzy_matches]]
                    ),
                    matched_regex=matched_regex,
                    matched_tags=matched_tags,
                )
                existing_rule_ids = {
                    existing.rule_id for existing in hits_by_sentence[sentence.sentence_id]
                }
                if matched_rule.rule_id not in existing_rule_ids:
                    hits_by_sentence[sentence.sentence_id].append(matched_rule)

        sentence_hits: list[SentenceRuleHit] = []
        matched_rules_map: dict[str, MatchedRule] = {}
        for sentence in sentences:
            sentence_rules = hits_by_sentence.get(sentence.sentence_id, [])
            if not sentence_rules:
                continue
            sentence_rules.sort(
                key=lambda item: (self._risk_score(item.severity), item.similarity_score),
                reverse=True,
            )
            sentence_hits.append(
                SentenceRuleHit(
                    sentence_id=sentence.sentence_id,
                    sentence=sentence.text,
                    start=sentence.start,
                    end=sentence.end,
                    highlights=self._collect_highlights(
                        sentence.text,
                        candidate_hits_by_sentence.get(sentence.sentence_id, []),
                        sentence_rules,
                    ),
                    rules=sentence_rules,
                )
            )
            for rule in sentence_rules:
                matched_rules_map.setdefault(rule.rule_id, rule)

        risk_level = self._aggregate_risk_level(sentence_hits)
        matched_rules = sorted(
            matched_rules_map.values(),
            key=lambda item: (self._risk_score(item.severity), item.similarity_score),
            reverse=True,
        )
        return risk_level, sentence_hits, matched_rules

    def _collect_highlights(
        self,
        sentence: str,
        candidate_hits: list[CandidateTagHit],
        sentence_rules: list[MatchedRule],
    ) -> list[TextHighlight]:
        spans: dict[tuple[int, int, str], TextHighlight] = {}

        for hit in candidate_hits:
            if hit.match_start is None or hit.match_end is None or not hit.matched_text:
                continue
            self._add_highlight(
                spans,
                start=hit.match_start,
                end=hit.match_end,
                text=hit.matched_text,
                source=hit.trigger_type,
            )

        for rule in sentence_rules:
            for keyword in rule.matched_keywords:
                for match in re.finditer(re.escape(keyword), sentence, flags=re.IGNORECASE):
                    self._add_highlight(
                        spans,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(0),
                        source="keyword",
                    )
            for pattern in rule.matched_regex:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                except re.error:
                    continue
                for match in compiled.finditer(sentence):
                    if not match.group(0):
                        continue
                    self._add_highlight(
                        spans,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(0),
                        source="regex",
                    )

        return sorted(spans.values(), key=lambda item: (item.start, item.end))

    def _add_highlight(
        self,
        spans: dict[tuple[int, int, str], TextHighlight],
        *,
        start: int,
        end: int,
        text: str,
        source: str,
    ) -> None:
        if start < 0 or end <= start:
            return

        key = (start, end, text)
        spans.setdefault(
            key,
            TextHighlight(
                start=start,
                end=end,
                text=text,
                source=source,
            ),
        )

    def _aggregate_risk_level(self, sentence_hits: list[SentenceRuleHit]) -> RiskLevel:
        if not sentence_hits:
            return RiskLevel.NONE

        max_score = max(self._risk_score(rule.severity) for hit in sentence_hits for rule in hit.rules)
        return {
            3: RiskLevel.HIGH,
            2: RiskLevel.MEDIUM,
            1: RiskLevel.LOW,
        }.get(max_score, RiskLevel.NONE)

    def _risk_score(self, risk_level: RiskLevel) -> int:
        mapping = {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }
        return mapping[risk_level]

    def _collect_fuzzy_matches(
        self,
        sentence: str,
        rule_keywords: list[str],
        matched_keywords: list[str],
    ) -> list[FuzzyMatchResult]:
        exact_keyword_set = {keyword.lower() for keyword in matched_keywords}
        results: list[FuzzyMatchResult] = []
        seen_queries: set[str] = set()
        for keyword in rule_keywords:
            if keyword.lower() in exact_keyword_set or keyword in seen_queries:
                continue
            fuzzy_match = find_fuzzy_match(sentence, keyword)
            if not fuzzy_match:
                continue
            results.append(fuzzy_match)
            seen_queries.add(keyword)
        return results

    def _semantic_support_score(
        self,
        sentence: str,
        rule_title: str,
        rule_content: str,
        rule_keywords: list[str],
    ) -> float:
        candidates = [rule_title, *rule_keywords[:8]]
        if rule_content:
            candidates.append(rule_content[:120])
        return max((text_similarity(sentence, candidate) for candidate in candidates if candidate), default=0.0)

    def _dedupe_values(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
