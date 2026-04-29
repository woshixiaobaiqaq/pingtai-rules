from __future__ import annotations

from app.services.candidate_screening import CandidateScreeningService
from app.services.text_processing import TextProcessor


def test_candidate_screening_detects_keyword_and_regex_hits() -> None:
    processor = TextProcessor()
    screening_service = CandidateScreeningService()
    content = "这个方法保证你7天回本，评论区留言领取资料。"

    segments = processor.split_sentences(content)
    hits = screening_service.screen(segments)
    tags = {(hit.tag, hit.trigger_type) for hit in hits}

    assert ("absolute_guarantee", "keyword") in tags
    assert ("financial_promise", "regex") in tags
    assert ("traffic_inducement", "regex") in tags


def test_candidate_screening_detects_douyin_platform_rule_tags() -> None:
    processor = TextProcessor()
    screening_service = CandidateScreeningService()
    content = "未成年人抽烟喝酒还飙车闯红灯，评论区扣1看短剧免费看全集。"

    segments = processor.split_sentences(content)
    hits = screening_service.screen(segments)
    tags = {hit.tag for hit in hits}

    assert "minor_protection" in tags
    assert "unsafe_behavior" in tags
    assert "interaction_manipulation" in tags
    assert "short_drama_promotion" in tags


def test_candidate_screening_returns_match_offsets() -> None:
    processor = TextProcessor()
    screening_service = CandidateScreeningService()
    content = "孩子因为辍学问题引发争议。"

    segments = processor.split_sentences(content)
    hits = screening_service.screen(segments)
    target = next(hit for hit in hits if hit.tag == "minor_protection" and hit.trigger_value == "辍学")

    assert target.matched_text == "辍学"
    assert target.match_start == content.index("辍学")
    assert target.match_end == target.match_start + len("辍学")


def test_candidate_screening_detects_xiaohongshu_platform_rule_tags() -> None:
    processor = TextProcessor()
    screening_service = CandidateScreeningService()
    content = "前大厂高管创业后年入百万，无广亲测有效，想买的加微信进群。"

    segments = processor.split_sentences(content)
    hits = screening_service.screen(segments)
    tags = {hit.tag for hit in hits}

    assert "persona_fabrication" in tags
    assert "false_review" in tags
    assert "traffic_inducement" in tags


def test_candidate_screening_detects_fuzzy_keyword_hits() -> None:
    processor = TextProcessor()
    screening_service = CandidateScreeningService()
    content = "点赞再关注，评论区留言领取资料。"

    segments = processor.split_sentences(content)
    hits = screening_service.screen(segments)
    fuzzy_hit = next(
        hit
        for hit in hits
        if hit.tag == "interaction_manipulation" and hit.trigger_type == "fuzzy_keyword"
    )

    assert fuzzy_hit.trigger_value == "点赞关注"
    assert "点赞" in (fuzzy_hit.matched_text or "")
    assert "关注" in (fuzzy_hit.matched_text or "")


def test_candidate_screening_detects_video_channel_specific_terms() -> None:
    processor = TextProcessor()
    screening_service = CandidateScreeningService()
    content = "加微信进群领取资料，保证7天回本；这款保健品根治高血压，视频画面花屏卡顿。"

    segments = processor.split_sentences(content)
    hits = screening_service.screen(segments)
    tags = {hit.tag for hit in hits}

    assert "traffic_inducement" in tags
    assert "financial_promise" in tags
    assert "medical_claim" in tags
    assert "content_quality_issue" in tags
