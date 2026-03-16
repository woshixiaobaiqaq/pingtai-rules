from __future__ import annotations

from app.db.models import Platform, RiskLevel
from app.schemas.common import RewriteOptions, SentenceRuleHit, SentenceSegment

SAFE_REPLACEMENTS = {
    "保证": "尽量",
    "确保": "帮助",
    "绝对": "相对",
    "100%": "尽可能",
    "包过": "系统提升通过概率",
    "根治": "改善",
    "治愈": "缓解",
    "稳赚": "争取更稳妥地提升收益",
    "暴富": "改善收入表现",
    "保本": "控制风险",
    "回本": "缩短投入回收周期",
    "加微信": "通过平台内公开方式沟通",
    "私信": "站内咨询",
    "扫码": "查看公开说明",
}

BALANCED_REPLACEMENTS = {
    "保证": "更有机会",
    "确保": "有助于",
    "绝对": "通常",
    "100%": "更高概率",
    "包过": "提高通过把握",
    "根治": "改善",
    "治愈": "改善",
    "稳赚": "更稳妥地提升收益",
    "暴富": "提升收入可能",
    "保本": "尽量控制风险",
    "回本": "优化投入回收周期",
    "加微信": "通过平台内沟通",
    "私信": "站内留言",
    "扫码": "查看说明",
}

CONVERSION_REPLACEMENTS = {
    "保证": "帮助你更清晰地执行",
    "确保": "帮助你更稳定地执行",
    "绝对": "更可能",
    "100%": "更高概率",
    "包过": "更系统地准备",
    "根治": "持续改善",
    "治愈": "逐步改善",
    "稳赚": "更稳妥地提升结果",
    "暴富": "提升收入机会",
    "保本": "兼顾风险控制",
    "回本": "优化回收周期",
    "加微信": "在评论区回复关键词",
    "私信": "评论区互动",
    "扫码": "查看公开版资料",
}

PLATFORM_SUFFIX = {
    Platform.DOUYIN: " 如需进一步了解，请通过抖音站内公开互动获取信息。",
    Platform.XIAOHONGSHU: " 如需进一步了解，请通过小红书站内公开互动获取信息。",
    Platform.VIDEO_CHANNEL: " 如需进一步了解，请通过视频号站内公开互动获取信息。",
}


class RewriteService:
    def rewrite(
        self,
        *,
        platform: Platform,
        original_content: str,
        sentences: list[SentenceSegment],
        hit_sentences: list[SentenceRuleHit],
        risk_level: RiskLevel,
    ) -> tuple[RewriteOptions, str]:
        hit_map = {hit.sentence_id: hit for hit in hit_sentences}
        safe_text = self._rewrite_content(
            original_content, sentences, hit_map, SAFE_REPLACEMENTS, platform, "safe"
        )
        balanced_text = self._rewrite_content(
            original_content, sentences, hit_map, BALANCED_REPLACEMENTS, platform, "balanced"
        )
        conversion_text = self._rewrite_content(
            original_content, sentences, hit_map, CONVERSION_REPLACEMENTS, platform, "conversion"
        )
        revised_text = {
            RiskLevel.HIGH: safe_text,
            RiskLevel.MEDIUM: balanced_text,
            RiskLevel.LOW: conversion_text,
            RiskLevel.NONE: original_content,
        }[risk_level]
        return (
            RewriteOptions(
                safe=safe_text,
                balanced=balanced_text,
                conversion=conversion_text,
            ),
            revised_text,
        )

    def _rewrite_content(
        self,
        original_content: str,
        sentences: list[SentenceSegment],
        hit_map: dict[int, SentenceRuleHit],
        replacements: dict[str, str],
        platform: Platform,
        mode: str,
    ) -> str:
        rebuilt: list[str] = []
        cursor = 0
        for sentence in sentences:
            rebuilt.append(original_content[cursor : sentence.start])
            replacement = original_content[sentence.start : sentence.end]
            hit = hit_map.get(sentence.sentence_id)
            if hit:
                replacement = self._rewrite_sentence(sentence.text, hit, replacements, platform, mode)
            rebuilt.append(replacement)
            cursor = sentence.end
        rebuilt.append(original_content[cursor:])
        return "".join(rebuilt).strip()

    def _rewrite_sentence(
        self,
        sentence: str,
        hit: SentenceRuleHit,
        replacements: dict[str, str],
        platform: Platform,
        mode: str,
    ) -> str:
        rewritten = sentence
        for source, target in replacements.items():
            rewritten = rewritten.replace(source, target)

        tags = {tag for rule in hit.rules for tag in rule.matched_tags}
        if "traffic_inducement" in tags and mode == "conversion":
            rewritten = rewritten.replace("评论区互动领取", "评论区回复关键词获取公开版资料")
            rewritten = rewritten.replace("评论区互动", "评论区回复关键词")
        if "absolute_guarantee" in tags and "效果因人而异" not in rewritten:
            rewritten = f"{rewritten.rstrip('。')}，效果因人而异。"
        if "financial_promise" in tags and "需结合实际情况判断" not in rewritten:
            rewritten = f"{rewritten.rstrip('。')}，需结合实际情况判断。"
        if "medical_claim" in tags and "不替代专业意见" not in rewritten:
            rewritten = f"{rewritten.rstrip('。')}，不替代专业意见。"
        if "traffic_inducement" in tags and mode != "conversion":
            rewritten = rewritten.rstrip("。") + PLATFORM_SUFFIX[platform]
        return rewritten

