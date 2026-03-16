from __future__ import annotations

from app.services.local_rule_source import get_local_rule_repository


def test_local_rule_repository_loads_douyin_rules_from_manifest() -> None:
    repository = get_local_rule_repository()

    rules, total = repository.list_rules(platform="douyin", limit=50, offset=0)

    assert total >= 16
    assert rules
    assert all(rule.platform.value == "douyin" for rule in rules)


def test_local_rule_repository_search_by_tags_returns_douyin_hits() -> None:
    repository = get_local_rule_repository()

    hits = repository.search_by_tags("douyin", {"minor_protection", "unsafe_behavior"}, limit=20)

    assert hits
    assert any("minor_protection" in hit.matched_tags or "unsafe_behavior" in hit.matched_tags for hit in hits)


def test_local_rule_repository_loads_xiaohongshu_rules_from_manifest() -> None:
    repository = get_local_rule_repository()

    rules, total = repository.list_rules(platform="xiaohongshu", limit=50, offset=0)

    assert total >= 100
    assert rules
    assert all(rule.platform.value == "xiaohongshu" for rule in rules)
    assert any(rule.rule_code.startswith("XHS-MAN-") for rule in rules)


def test_local_rule_repository_loads_video_channel_rules_from_manifest() -> None:
    repository = get_local_rule_repository()

    rules, total = repository.list_rules(platform="video_channel", limit=50, offset=0)
    all_video_rules, _ = repository.list_rules(platform="video_channel", limit=500, offset=0)

    assert total >= 300
    assert rules
    assert all(rule.platform.value == "video_channel" for rule in rules)
    assert any(rule.rule_code.startswith("VC-") for rule in all_video_rules)
    assert any(rule.rule_code.startswith("VC-STD-") for rule in all_video_rules)
