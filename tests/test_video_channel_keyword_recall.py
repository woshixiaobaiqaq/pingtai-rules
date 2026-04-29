from __future__ import annotations

from app.db.models import Platform, RiskLevel
from app.services.audit_orchestrator import AuditOrchestratorService
from app.services.local_rule_source import get_local_rule_repository


def test_video_channel_audit_uses_expanded_keyword_rules() -> None:
    get_local_rule_repository.cache_clear()
    service = AuditOrchestratorService(None, get_local_rule_repository())

    response = service.audit(
        content="保证7天回本，加微信进群领取资料。",
        platforms=[Platform.VIDEO_CHANNEL],
        persist=False,
    )

    result = response.report.platform_results[0]
    matched_keywords = {
        keyword
        for rule in result.matched_rules
        for keyword in rule.matched_keywords
    }
    matched_regex = {
        pattern
        for rule in result.matched_rules
        for pattern in rule.matched_regex
    }

    assert result.risk_level != RiskLevel.NONE
    assert "回本" in matched_keywords or any("回本" in pattern for pattern in matched_regex)
    assert "加微信" in matched_keywords or any("微信" in pattern for pattern in matched_regex)
    assert "点赞|评论|关注|分享" not in matched_regex
