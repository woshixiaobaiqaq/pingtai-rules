from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_rule_library_manifest_and_douyin_bundle_exist() -> None:
    manifest_path = PROJECT_ROOT / "data/rule_library/manifest.json"
    bundle_path = PROJECT_ROOT / "data/rule_library/douyin/rules.json"
    xhs_bundle_path = PROJECT_ROOT / "data/rule_library/xiaohongshu/rules.json"
    vc_bundle_path = PROJECT_ROOT / "data/rule_library/video_channel/rules.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    xhs_bundle = json.loads(xhs_bundle_path.read_text(encoding="utf-8"))
    vc_bundle = json.loads(vc_bundle_path.read_text(encoding="utf-8"))

    assert manifest["platforms"][0]["platform"] == "douyin"
    assert manifest["platforms"][0]["status"] == "ready"
    assert manifest["platforms"][1]["platform"] == "xiaohongshu"
    assert manifest["platforms"][1]["status"] == "ready"
    assert manifest["platforms"][2]["platform"] == "video_channel"
    assert manifest["platforms"][2]["status"] == "ready"
    assert len(bundle["rules"]) == 16
    assert len(xhs_bundle["rules"]) >= 100
    assert len(vc_bundle["rules"]) >= 100


def test_douyin_rule_bundle_has_unique_ids_and_platform_split() -> None:
    bundle_path = PROJECT_ROOT / "data/rule_library/douyin/rules.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    rule_ids = [item["rule_id"] for item in bundle["rules"]]

    assert len(rule_ids) == len(set(rule_ids))
    assert all(item["platform"] == "douyin" for item in bundle["rules"])
    assert all(item["metadata"]["commerce_id"] for item in bundle["rules"])


def test_xiaohongshu_rule_bundle_has_unique_ids_and_platform_split() -> None:
    bundle_path = PROJECT_ROOT / "data/rule_library/xiaohongshu/rules.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    rule_ids = [item["rule_id"] for item in bundle["rules"]]

    assert len(rule_ids) == len(set(rule_ids))
    assert all(item["platform"] == "xiaohongshu" for item in bundle["rules"])
    assert all(item["metadata"]["source_urls"] for item in bundle["rules"])
    assert any(item["rule_id"].startswith("XHS-MAN-") for item in bundle["rules"])


def test_xiaohongshu_manual_rule_content_trims_ocr_headers() -> None:
    bundle_path = PROJECT_ROOT / "data/rule_library/xiaohongshu/rules.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    manual_rule = next(item for item in bundle["rules"] if item["rule_id"] == "XHS-MAN-001")

    assert manual_rule["content"].startswith("平台坚决反对各种形式的人身伤害行为")
    assert not manual_rule["content"].startswith("违法违规-违法行为")


def test_video_channel_rule_bundle_has_unique_ids_and_local_images() -> None:
    bundle_path = PROJECT_ROOT / "data/rule_library/video_channel/rules.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    rule_ids = [item["rule_id"] for item in bundle["rules"]]

    assert len(rule_ids) == len(set(rule_ids))
    assert all(item["platform"] == "video_channel" for item in bundle["rules"])
    assert any(item["metadata"]["image_assets"] for item in bundle["rules"])
    assert all(item["metadata"]["source_urls"] for item in bundle["rules"])
    assert any(item["rule_id"].startswith("VC-STD-") for item in bundle["rules"])


def test_video_channel_operation_standards_rules_are_merged_without_reference_stub() -> None:
    bundle_path = PROJECT_ROOT / "data/rule_library/video_channel/rules.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    assert "VC-STD-5-21" not in {item["rule_id"] for item in bundle["rules"]}

    ai_rule = next(item for item in bundle["rules"] if item["rule_id"] == "VC-STD-6-4")
    minor_rule = next(item for item in bundle["rules"] if item["rule_id"] == "VC-STD-5-7-9")

    assert ai_rule["metadata"]["source_type"] == "official_operation_standards"
    assert ai_rule["metadata"]["source_urls"] == [
        "https://weixin.qq.com/cgi-bin/readtemplate?lang=zh_CN&t=weixin_agreement&s=video"
    ]
    assert "应以显著方式予以标识" in ai_rule["content"]
    assert "未成年人厌学弃学" in minor_rule["content"]
