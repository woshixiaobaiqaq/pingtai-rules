from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/m/亿一的AI小助理/open-codex/platform-content-audit")
XHS_RULE_DIR = ROOT / "data/rule_library/xiaohongshu"
PROCESSED_ROOT = ROOT / "data/source_archives/xiaohongshu_creator_center_manual/processed"
SEED_RULES_PATH = XHS_RULE_DIR / "rules_seed_20260312.json"
OUTPUT_RULES_PATH = XHS_RULE_DIR / "rules.json"
OUTPUT_CATALOG_PATH = XHS_RULE_DIR / "catalog.json"

STOPWORDS = {
    "规则说明",
    "规则",
    "说明",
    "平台",
    "小红书",
    "内容",
    "行为",
    "可能存在",
    "问题",
    "场景",
    "用户",
    "进行",
    "发布",
    "相关",
    "包括但不限于",
    "违规",
    "违法违规",
    "商业秩序",
    "内容质量",
    "平台秩序",
    "社区氛围",
    "色情低俗",
    "公序良俗",
    "原创保护",
    "风险行为",
    "医疗医美",
    "涉未成年",
}

CATEGORY_SEVERITY = {
    "违法违规": "high",
    "医疗医美": "high",
    "风险行为": "high",
    "平台秩序": "high",
    "内容质量": "medium",
    "商业秩序": "high",
    "原创保护": "medium",
    "涉未成年": "high",
    "社区氛围": "high",
    "色情低俗": "high",
    "公序良俗": "medium",
}


@dataclass(frozen=True, slots=True)
class Heuristic:
    match: tuple[str, ...]
    tags: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    regex_patterns: tuple[str, ...] = ()
    severity: str | None = None


HEURISTICS = [
    Heuristic(("导流", "站外", "交易"), ("traffic_inducement",), (), (r"(微信|vx|v信|二维码)",)),
    Heuristic(("虚假测评", "合集测评"), ("false_review",)),
    Heuristic(
        ("虚假营销", "低质营销", "夸大宣传", "虚假宣传"),
        ("marketing_violation",),
        (),
        (r"100%|全网第?一|全网最低",),
    ),
    Heuristic(("虚构体验", "虚构人设", "冒充他人", "虚构内容", "博眼球编故事"), ("persona_fabrication",)),
    Heuristic(("搬运", "转载", "原创"), ("originality_violation",)),
    Heuristic(("隐私", "曝光", "网暴", "骚扰", "攻击他人"), ("rights_infringement",)),
    Heuristic(("未成年", "早婚早孕", "防沉迷"), ("minor_protection",)),
    Heuristic(("裸露", "性行为", "性服务", "两性", "陪侍"), ("sexual_content",)),
    Heuristic(("自我伤害", "危险地带", "公共安全"), ("unsafe_behavior",)),
    Heuristic(("医疗", "医美", "药物"), ("medical_content", "medical_claim"), (), (r"根治|治愈|包治",)),
    Heuristic(("金融", "理财"), ("financial_promise",), (), (r"\d+天回本|零风险",)),
    Heuristic(("剧情演绎", "封面标题低差", "诱导互动"), ("clickbait_content", "interaction_manipulation")),
    Heuristic(("引人不适", "血腥暴力"), ("disturbing_content",)),
    Heuristic(("矩阵号", "养号做号", "频发广告"), ("duplicate_content", "marketing_violation")),
    Heuristic(("国家", "军警", "出版物", "管制品"), ("illegal_activity",)),
    Heuristic(("拜金炫富", "饭圈", "迷信", "不良婚恋观", "歧视"), ("public_ethics",)),
]

PHRASE_LEXICON = [
    "未成年",
    "早婚",
    "早孕",
    "违法犯罪",
    "性侵害",
    "成人化",
    "医疗医美",
    "医疗",
    "医美",
    "高危",
    "药物",
    "自我伤害",
    "理财",
    "金融",
    "兼职",
    "诈骗",
    "虚假活动",
    "虚构身份",
    "引导",
    "站外",
    "导流",
    "养号",
    "做号",
    "网暴",
    "攻击",
    "隐私",
    "裸露",
    "性行为",
    "性服务",
    "两性",
    "饭圈",
    "追星",
    "炫富",
    "迷信",
    "歧视",
    "历史虚无主义",
    "搬运",
    "冒充",
    "虚假营销",
    "虚假测评",
    "夸大宣传",
    "标题低差",
    "诱导互动",
    "博眼球",
    "虚假谣言",
    "剧情演绎",
    "不真诚互动",
    "频发广告",
    "矩阵号",
    "违规交易",
    "危险品",
]


def latest_processed_catalog() -> Path:
    candidates = sorted(PROCESSED_ROOT.glob("processed_*/catalog.json"))
    if not candidates:
        raise FileNotFoundError(f"No processed creator center catalog found under {PROCESSED_ROOT}")
    return candidates[-1]


def split_title_terms(title: str) -> list[str]:
    pieces = re.split(r"[：:、/·\-\s与及和（）()]+", title)
    results = [piece for piece in pieces if 1 < len(piece) <= 12 and piece not in STOPWORDS]
    for phrase in PHRASE_LEXICON:
        if phrase in title and phrase not in results:
            results.append(phrase)
    return results


def dedupe_title(category_name: str, title: str, title_counter: Counter[tuple[str, str]]) -> str:
    key = (category_name, title)
    title_counter[key] += 1
    if title_counter[key] == 1:
        return title
    return f"{title}（{title_counter[key]}）"


def infer_tags_keywords_patterns(
    category_name: str,
    title: str,
    full_text: str,
) -> tuple[list[str], list[str], list[str], str, list[str]]:
    tags: set[str] = {
        f"xhs_manual_rule_{slugify(title)}",
        f"xhs_manual_category_{slugify(category_name)}",
    }
    keywords: list[str] = []
    regex_patterns: set[str] = set()
    severity = CATEGORY_SEVERITY.get(category_name, "medium")
    inferred_candidate_tags: set[str] = set()

    for term in split_title_terms(title):
        if term not in keywords:
            keywords.append(term)

    for rule in HEURISTICS:
        if any(token in title for token in rule.match):
            inferred_candidate_tags.update(rule.tags)
            for keyword in rule.keywords:
                if keyword not in keywords:
                    keywords.append(keyword)
            regex_patterns.update(rule.regex_patterns)
            if rule.severity == "high":
                severity = "high"
            elif rule.severity == "medium" and severity != "high":
                severity = "medium"

    return sorted(tags), keywords[:12], sorted(regex_patterns), severity, sorted(inferred_candidate_tags)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "rule"


def extract_rule_body(full_text: str) -> str:
    compact = re.sub(r"\s+", " ", full_text).strip()
    if not compact:
        return ""

    parts = re.split(r"规则说明[:：]?", compact, maxsplit=1)
    if len(parts) == 2:
        body = parts[1].strip()
        if body:
            return body
    return compact


def build_rule_content(title: str, full_text: str) -> str:
    cleaned = extract_rule_body(full_text)
    if len(cleaned) <= 420:
        return cleaned
    return f"{cleaned[:419]}…"


def build_catalog(manual_rules: list[dict], source_catalog_path: Path) -> dict:
    category_map: dict[str, list[dict]] = {}
    for rule in manual_rules:
        category_map.setdefault(rule["metadata"]["manual_category"], []).append(rule)

    return {
        "platform": "xiaohongshu",
        "version": datetime.now().strftime("%Y-%m-%d"),
        "status": "ready",
        "title": "小红书内容侧规则目录",
        "scope": "短视频、笔记与创作中心规则百科",
        "source_notes": [
            {
                "type": "seed_rule_bundle",
                "title": "2026-03-12 小红书内容侧规则主题库",
                "path": str(SEED_RULES_PATH),
            },
            {
                "type": "creator_center_manual_capture",
                "title": "创作中心规则百科手工截图归档",
                "path": str(source_catalog_path),
            },
        ],
        "categories": [
            {
                "category": category_name,
                "rule_count": len(items),
                "sample_titles": [item["title"] for item in items[:8]],
            }
            for category_name, items in sorted(category_map.items())
        ],
    }


def main() -> None:
    seed_rules = json.loads(SEED_RULES_PATH.read_text(encoding="utf-8"))
    processed_catalog_path = latest_processed_catalog()
    processed_catalog = json.loads(processed_catalog_path.read_text(encoding="utf-8"))

    manual_rules: list[dict] = []
    title_counter: Counter[tuple[str, str]] = Counter()
    sequence = 1

    for category in processed_catalog["categories"]:
        category_name = category["category_name"]
        if category_name == "大纲":
            continue
        for item in category["items"]:
            base_title = item["display_title"]
            display_title = dedupe_title(category_name, base_title, title_counter)
            tags, keywords, regex_patterns, severity, inferred_candidate_tags = infer_tags_keywords_patterns(
                category_name=category_name,
                title=display_title,
                full_text=item["ocr_full_text"],
            )
            manual_rules.append(
                {
                    "platform": "xiaohongshu",
                    "rule_id": f"XHS-MAN-{sequence:03d}",
                    "title": f"{category_name}：{display_title}",
                    "content": build_rule_content(display_title, item["ocr_full_text"]),
                    "source_url": None,
                    "severity": severity,
                    "tags": tags,
                    "keywords": keywords,
                    "regex_patterns": regex_patterns,
                    "metadata": {
                        "source_type": "creator_center_manual_capture",
                        "manual_category": category_name,
                        "manual_title": display_title,
                        "inferred_candidate_tags": inferred_candidate_tags,
                        "title_source": item["title_source"],
                        "ocr_confidence_avg": item["ocr_confidence_avg"],
                        "flags": item["flags"],
                        "source_urls": [item["image_path"]],
                        "processed_catalog_path": str(processed_catalog_path),
                        "image_name": item["image_name"],
                    },
                }
            )
            sequence += 1

    merged_rules = list(seed_rules["rules"]) + manual_rules
    OUTPUT_RULES_PATH.write_text(
        json.dumps({"rules": merged_rules}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUTPUT_CATALOG_PATH.write_text(
        json.dumps(build_catalog(manual_rules, processed_catalog_path), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "seed_rules": len(seed_rules["rules"]),
                "manual_rules": len(manual_rules),
                "merged_rules": len(merged_rules),
                "rules_path": str(OUTPUT_RULES_PATH),
                "catalog_path": str(OUTPUT_CATALOG_PATH),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
