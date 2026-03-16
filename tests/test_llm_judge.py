from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.db.models import Platform, RiskLevel
from app.schemas.common import CandidateTagHit, SentenceSegment
from app.services.llm_judge import RuleBoundJudgeService
from app.services.local_rule_source import LocalRule, LocalRuleTag
from app.services.rule_recall import RecallCandidate


def test_judge_returns_highlights_for_hit_sentence() -> None:
    judge_service = RuleBoundJudgeService()
    sentence = "孩子因为辍学问题引发争议。"
    sentences = [SentenceSegment(sentence_id=1, text=sentence, start=0, end=len(sentence))]
    candidate_hits = [
        CandidateTagHit(
            tag="minor_protection",
            trigger_type="keyword",
            trigger_value="辍学",
            sentence_id=1,
            sentence=sentence,
            matched_text="辍学",
            match_start=4,
            match_end=6,
        )
    ]
    recalled_rules = [
        RecallCandidate(
            rule=LocalRule(
                id=uuid4(),
                platform=Platform.DOUYIN,
                rule_code="DY-CAT-005",
                title="未成年人",
                content="禁止危害未成年人身心健康、安全和价值观的内容。",
                source_url=None,
                severity=RiskLevel.HIGH,
                keywords=["辍学"],
                regex_patterns=[],
                rule_metadata={},
                enabled=True,
                tags=[LocalRuleTag(tag="minor_protection")],
                embeddings=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            matched_tags={"minor_protection"},
            matched_keywords={"辍学"},
            similarity_score=0.4,
        )
    ]

    _, sentence_hits, matched_rules = judge_service.judge(
        platform=Platform.DOUYIN,
        sentences=sentences,
        candidate_hits=candidate_hits,
        recalled_rules=recalled_rules,
    )

    assert len(sentence_hits) == 1
    assert sentence_hits[0].sentence == sentence
    assert sentence_hits[0].highlights[0].text == "辍学"
    assert sentence_hits[0].highlights[0].start == 4
    assert sentence_hits[0].highlights[0].end == 6
    assert matched_rules[0].matched_keywords == ["辍学"]


def test_judge_accepts_fuzzy_keyword_match() -> None:
    judge_service = RuleBoundJudgeService()
    sentence = "点赞再关注就能继续看。"
    sentences = [SentenceSegment(sentence_id=1, text=sentence, start=0, end=len(sentence))]
    candidate_hits = [
        CandidateTagHit(
            tag="interaction_manipulation",
            trigger_type="fuzzy_keyword",
            trigger_value="点赞关注",
            sentence_id=1,
            sentence=sentence,
            matched_text="点赞再关注",
            match_start=0,
            match_end=5,
        )
    ]
    recalled_rules = [
        RecallCandidate(
            rule=LocalRule(
                id=uuid4(),
                platform=Platform.DOUYIN,
                rule_code="DY-CAT-006",
                title="诱导互动",
                content="不得通过点赞关注等形式诱导用户互动。",
                source_url=None,
                severity=RiskLevel.MEDIUM,
                keywords=["点赞关注"],
                regex_patterns=[],
                rule_metadata={},
                enabled=True,
                tags=[LocalRuleTag(tag="interaction_manipulation")],
                embeddings=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            matched_tags={"interaction_manipulation"},
            matched_keywords=set(),
            similarity_score=0.2,
        )
    ]

    _, sentence_hits, matched_rules = judge_service.judge(
        platform=Platform.DOUYIN,
        sentences=sentences,
        candidate_hits=candidate_hits,
        recalled_rules=recalled_rules,
    )

    assert len(sentence_hits) == 1
    assert sentence_hits[0].highlights[0].text == "点赞再关注"
    assert "模糊命中" in matched_rules[0].reason
    assert matched_rules[0].matched_keywords == ["点赞再关注"]
