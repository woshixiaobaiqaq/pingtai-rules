from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path("/Users/m/亿一的AI小助理/open-codex/platform-content-audit")
RULE_DIR = ROOT / "data/rule_library/video_channel"
RULES_PATH = RULE_DIR / "rules.json"
CATALOG_PATH = RULE_DIR / "catalog.json"

GUIDE_ARCHIVE_DIR = ROOT / "data/source_archives/video_channel_video_guide/full_archive_20260316"
GUIDE_URL = "https://weixin.qq.com/cgi-bin/readtemplate?lang=zh_CN&t=weixin_agreement&s=video_guide"

STANDARDS_ARCHIVE_DIR = ROOT / "data/source_archives/video_channel_operation_standards/full_archive_20260316"
STANDARDS_URL = "https://weixin.qq.com/cgi-bin/readtemplate?lang=zh_CN&t=weixin_agreement&s=video"
STANDARDS_FALLBACK_RAW_PATH = Path("/tmp/video_rules_main.html")

GUIDE_SECTION_SEVERITY = {
    "1": "medium",
    "2": "high",
    "3": "high",
    "4": "high",
    "5": "high",
    "6": "medium",
    "7": "high",
    "8": "medium",
    "9": "high",
    "10": "high",
    "11": "high",
    "12": "medium",
    "13": "high",
    "14": "high",
    "15": "medium",
    "16": "low",
}

STANDARDS_SECTION_SEVERITY = {
    "1": "low",
    "2": "low",
    "3": "medium",
    "4": "high",
    "5": "high",
    "6": "medium",
    "7": "low",
}

CHINESE_SECTION_NUMBERS = {
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
    "十一": "11",
    "十二": "12",
    "十三": "13",
    "十四": "14",
    "十五": "15",
    "十六": "16",
}
ARABIC_TO_CHINESE_SECTION = {value: key for key, value in CHINESE_SECTION_NUMBERS.items()}

TAG_HEURISTICS: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = [
    (
        ("医疗", "医美", "药品", "医疗器械", "保健", "诊疗", "中医"),
        ("medical_content", "medical_claim"),
        (r"治愈|功效",),
    ),
    (
        ("理财", "投资", "财经", "股票", "基金", "金融", "荐股", "期货"),
        ("financial_promise",),
        (r"高收益|短期|保本",),
    ),
    (("未成年人", "抽烟", "喝酒", "纹身", "校园暴力", "厌学", "弃学"), ("minor_protection",), (r"未成年",)),
    (("搬运", "抄袭", "洗稿", "著作权", "版权", "知识产权"), ("originality_violation", "copyright_violation"), ()),
    (("低俗", "裸体", "性暗示", "色情", "隐私部位", "性器官"), ("sexual_content",), (r"性暗示|裸体",)),
    (("赌博", "传销", "外挂", "房卡", "诈骗", "钓鱼网站"), ("illegal_activity",), (r"赌博|传销|外挂|诈骗",)),
    (("冒充", "姓名权", "肖像权", "名誉", "隐私", "商业秘密", "商标"), ("rights_infringement",), ()),
    (
        ("联系方式", "二维码", "引流", "导流", "私信", "链接", "域名"),
        ("traffic_inducement",),
        (r"二维码|联系方式|引流",),
    ),
    (
        ("虚假", "夸大", "误导", "新闻体", "难辨真伪", "标题", "不实信息"),
        ("marketing_violation", "clickbait_content"),
        (r"夸大|误导|虚假",),
    ),
    (
        ("作弊", "刷量", "刷粉", "造假", "账号买卖", "虚假注册", "批量注册"),
        ("duplicate_content",),
        (r"刷量|刷粉|造假",),
    ),
    (("辱骂", "歧视", "婚闹", "出轨", "虐待", "炫富", "卖惨"), ("public_ethics",), (r"歧视|婚闹|虐待|卖惨",)),
    (("黑边", "花屏", "卡顿", "口型", "字幕", "低质", "画质模糊"), ("content_quality_issue",), (r"花屏|卡顿|字幕",)),
    (
        ("点赞", "评论", "关注", "分享", "集赞", "抽奖机会", "诱导用户"),
        ("interaction_manipulation",),
        (r"点赞|评论|关注|分享",),
    ),
    (
        ("深度学习", "虚拟现实", "生成式人工智能", "AI", "合成", "虚假摆拍", "非真实音视频"),
        ("ai_generated_content",),
        (r"AI|深度学习|生成式人工智能|合成",),
    ),
]


@dataclass(slots=True)
class SourceSpec:
    key: str
    title: str
    url: str
    archive_dir: Path
    rule_id_prefix: str
    source_type: str
    section_severity: dict[str, str]
    intro_skip_text: str | None = None
    fallback_raw_paths: tuple[Path, ...] = ()
    image_dir: Path | None = None

    @property
    def raw_html_path(self) -> Path:
        return self.archive_dir / "raw" / f"{self.key}.html"

    @property
    def tokens_path(self) -> Path:
        return self.archive_dir / "page_tokens.json"

    @property
    def structured_path(self) -> Path:
        return self.archive_dir / "structured_sections.json"

    @property
    def archive_manifest_path(self) -> Path:
        return self.archive_dir / "archive_manifest.json"

    @property
    def local_html_path(self) -> Path:
        return self.archive_dir / "index_local.html"


GUIDE_SPEC = SourceSpec(
    key="video_guide",
    title="视频号常见违规内容概览",
    url=GUIDE_URL,
    archive_dir=GUIDE_ARCHIVE_DIR,
    rule_id_prefix="VC-",
    source_type="official_video_guide",
    section_severity=GUIDE_SECTION_SEVERITY,
    intro_skip_text="视频号常见违规内容概览",
    image_dir=GUIDE_ARCHIVE_DIR / "images",
)

STANDARDS_SPEC = SourceSpec(
    key="video_operation_standards",
    title="微信视频号运营规范",
    url=STANDARDS_URL,
    archive_dir=STANDARDS_ARCHIVE_DIR,
    rule_id_prefix="VC-STD-",
    source_type="official_operation_standards",
    section_severity=STANDARDS_SECTION_SEVERITY,
    fallback_raw_paths=(STANDARDS_FALLBACK_RAW_PATH,),
)

SOURCE_SPECS = (GUIDE_SPEC, STANDARDS_SPEC)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value).replace("\xa0", " ")).strip()


def normalize_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    return url


def slugify_rule_code(rule_code: str) -> str:
    return rule_code.replace(".", "-")


def slugify_value(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "rule"


def dedupe_preserve(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


@dataclass(slots=True)
class Token:
    kind: str
    text: str = ""
    src: str = ""
    links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuleAsset:
    caption: str
    remote_url: str
    local_path: str = ""


@dataclass(slots=True)
class RuleItem:
    rule_code: str
    title: str
    section_code: str
    section_title: str
    body: list[str] = field(default_factory=list)
    images: list[RuleAsset] = field(default_factory=list)
    video_links: list[dict[str, str]] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Section:
    section_code: str
    title: str
    notes: list[str] = field(default_factory=list)
    rules: list[RuleItem] = field(default_factory=list)


@dataclass(slots=True)
class SourceExtraction:
    spec: SourceSpec
    intro: str
    sections: list[Section]
    image_map: dict[str, str]
    rules: list[dict[str, object]]


class _TextContext:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.text_parts: list[str] = []
        self.links: list[str] = []


class VideoRuleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.in_capture = False
        self.capture_div_depth = 0
        self.context_stack: list[_TextContext] = []
        self.tokens: list[Token] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        class_names = set(attr_map.get("class", "").split())
        if not self.in_capture and tag == "div" and (
            attr_map.get("id") == "js_content" or "content_body" in class_names
        ):
            self.in_capture = True
            self.capture_div_depth = 1
            return

        if not self.in_capture:
            return

        if tag == "div":
            self.capture_div_depth += 1
            return

        if tag in {"ul", "ol"} and self.context_stack and self.context_stack[-1].tag == "li":
            self._flush_current_li_prefix()
            return

        if tag in {"p", "li", "h1", "h2"}:
            self.context_stack.append(_TextContext(tag))
            return

        if tag == "a" and self.context_stack:
            href = normalize_url(attr_map.get("href", ""))
            if href:
                self.context_stack[-1].links.append(href)
            return

        if tag == "img":
            src = normalize_url(attr_map.get("src", ""))
            if src:
                self.tokens.append(Token(kind="image", src=src))

    def handle_endtag(self, tag: str) -> None:
        if not self.in_capture:
            return

        if tag in {"p", "li", "h1", "h2"} and self.context_stack and self.context_stack[-1].tag == tag:
            context = self.context_stack.pop()
            text = normalize_space("".join(context.text_parts))
            if text:
                self.tokens.append(Token(kind="text", text=text, links=dedupe_preserve(context.links)))
            return

        if tag == "div":
            self.capture_div_depth -= 1
            if self.capture_div_depth <= 0:
                self.in_capture = False

    def handle_data(self, data: str) -> None:
        if not self.in_capture or not self.context_stack:
            return
        self.context_stack[-1].text_parts.append(data)

    def _flush_current_li_prefix(self) -> None:
        context = self.context_stack[-1]
        text = normalize_space("".join(context.text_parts))
        if not text:
            return
        self.tokens.append(Token(kind="text", text=text, links=dedupe_preserve(context.links)))
        context.text_parts.clear()
        context.links.clear()


def fetch_html(spec: SourceSpec) -> str:
    for path in (spec.raw_html_path, *spec.fallback_raw_paths):
        if path.exists():
            return path.read_text(encoding="utf-8")

    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        response = client.get(spec.url)
        response.raise_for_status()
        return response.text


def parse_tokens(html_text: str) -> list[Token]:
    parser = VideoRuleHTMLParser()
    parser.feed(html_text)
    return parser.tokens


def match_section_heading(text: str) -> tuple[str, str] | None:
    match = re.match(r"^(\d+)\.\s*(.+)$", text)
    if match:
        return match.group(1), match.group(2).strip("；;。 ")

    match = re.match(r"^([一二三四五六七八九十]+)、\s*(.+)$", text)
    if not match:
        return None
    section_code = CHINESE_SECTION_NUMBERS.get(match.group(1))
    if not section_code:
        return None
    return section_code, match.group(2).strip("；;。 ")


def match_rule_heading(text: str) -> tuple[str, str] | None:
    match = re.match(r"^((?:\d+\.)+\d+)\s*(.+)$", text)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def split_rule_title_body(text: str) -> tuple[str, str]:
    if "：" in text:
        title, body = text.split("：", 1)
        return title.strip("；;。 "), body.strip()
    if ":" in text:
        title, body = text.split(":", 1)
        return title.strip("；;。 "), body.strip()
    return text.strip("；;。 "), ""


def infer_keywords(section_title: str, rule_title: str, body_parts: list[str]) -> list[str]:
    source_text = " ".join([section_title, rule_title, *body_parts])
    candidates = [section_title, rule_title]
    for phrase in (
        "未成年人",
        "抽烟",
        "喝酒",
        "赌博",
        "传销",
        "外挂",
        "二维码",
        "引流",
        "医美",
        "医疗",
        "理财",
        "股票",
        "夸大",
        "虚假",
        "版权",
        "搬运",
        "抄袭",
        "黑边",
        "花屏",
        "卡顿",
        "口型",
        "字幕",
        "婚闹",
        "歧视",
        "辱骂",
        "虐待",
        "作弊",
        "刷量",
        "账号买卖",
        "AI",
        "生成式人工智能",
        "深度学习",
        "集赞",
        "点赞",
        "评论",
        "关注",
    ):
        if phrase in source_text:
            candidates.append(phrase)

    results: list[str] = []
    for item in candidates:
        value = item.strip()
        if value and value not in results:
            results.append(value)
    return results[:12]


def infer_tags_and_patterns(
    section_title: str,
    rule_title: str,
    body_parts: list[str],
) -> tuple[list[str], list[str], list[str]]:
    source_text = " ".join([section_title, rule_title, *body_parts])
    tags = {f"vc_section_{slugify_value(section_title)}", f"vc_rule_{slugify_value(rule_title)}"}
    inferred_tags: set[str] = set()
    regex_patterns: set[str] = set()
    for keywords, matched_tags, patterns in TAG_HEURISTICS:
        if any(keyword in source_text for keyword in keywords):
            inferred_tags.update(matched_tags)
            regex_patterns.update(patterns)
    return sorted(tags), sorted(inferred_tags), sorted(regex_patterns)


def build_sections(spec: SourceSpec, tokens: list[Token]) -> tuple[str, list[Section]]:
    intro = ""
    sections: list[Section] = []
    current_section: Section | None = None
    current_rule: RuleItem | None = None
    pending_caption = ""

    for token in tokens:
        if token.kind == "text":
            text = token.text
            if spec.intro_skip_text and text == spec.intro_skip_text:
                continue

            section_match = match_section_heading(text)
            if section_match and not match_rule_heading(text):
                current_section = Section(section_code=section_match[0], title=section_match[1])
                sections.append(current_section)
                current_rule = None
                pending_caption = ""
                continue

            rule_match = match_rule_heading(text)
            if rule_match and current_section is not None:
                title, body_intro = split_rule_title_body(rule_match[1])
                current_rule = RuleItem(
                    rule_code=rule_match[0],
                    title=title,
                    section_code=current_section.section_code,
                    section_title=current_section.title,
                )
                if body_intro:
                    current_rule.body.append(body_intro)
                current_section.rules.append(current_rule)
                pending_caption = ""
                continue

            if current_rule is None:
                if current_section is None:
                    intro = " ".join(part for part in [intro, text] if part).strip()
                elif text != "包括但不限于：":
                    current_section.notes.append(text)
                continue

            if "违规案例" in text or "点击查看完整案例视频" in text:
                pending_caption = text
                for link in token.links:
                    if link.endswith(".mp4"):
                        current_rule.video_links.append({"caption": text, "remote_url": link})
                    else:
                        current_rule.references.append(link)
                continue

            if token.links:
                current_rule.references.extend(link for link in token.links if not link.endswith(".mp4"))

            if text != "包括但不限于：":
                current_rule.body.append(text)
            continue

        if token.kind == "image" and current_rule is not None:
            current_rule.images.append(RuleAsset(caption=pending_caption, remote_url=token.src))
            pending_caption = ""

    return intro, sections


def resolve_local_images(spec: SourceSpec, sections: list[Section]) -> dict[str, str]:
    if spec.image_dir is None:
        return {}

    image_map: dict[str, str] = {}
    has_images = any(rule.images for section in sections for rule in section.rules)
    if not has_images:
        return image_map

    spec.image_dir.mkdir(parents=True, exist_ok=True)
    for section in sections:
        for rule in section.rules:
            for asset in rule.images:
                if asset.remote_url in image_map:
                    asset.local_path = image_map[asset.remote_url]
                    continue

                parsed = urlparse(asset.remote_url)
                file_name = Path(parsed.path).name
                destination = spec.image_dir / file_name
                if not destination.exists():
                    raise FileNotFoundError(f"Missing localized image for {asset.remote_url}: {destination}")
                relative_path = str(destination.relative_to(ROOT))
                image_map[asset.remote_url] = relative_path
                asset.local_path = relative_path
    return image_map


def build_local_html(spec: SourceSpec, html_text: str, image_map: dict[str, str]) -> str:
    if not image_map:
        return html_text

    local_html = html_text
    archive_root = spec.archive_dir.relative_to(ROOT)
    for remote_url, relative_path in image_map.items():
        archive_relative = str(Path(relative_path).relative_to(archive_root))
        local_html = local_html.replace(remote_url, archive_relative)
        local_html = local_html.replace(remote_url.removeprefix("https:"), archive_relative)
    return local_html


def build_source_url(spec: SourceSpec, rule: RuleItem) -> str:
    if spec is GUIDE_SPEC:
        return f"{spec.url}#{rule.section_code}"

    chinese_section = ARABIC_TO_CHINESE_SECTION.get(rule.section_code)
    if not chinese_section:
        return spec.url
    return f"{spec.url}#{chinese_section}-{rule.section_title}"


def should_include_rule(spec: SourceSpec, rule: RuleItem) -> bool:
    return not (spec is STANDARDS_SPEC and rule.rule_code == "5.21")


def build_rule_payload(spec: SourceSpec, rule: RuleItem) -> dict[str, object]:
    tags, inferred_tags, regex_patterns = infer_tags_and_patterns(rule.section_title, rule.title, rule.body)
    keywords = infer_keywords(rule.section_title, rule.title, rule.body)
    content_parts = [part for part in rule.body if part]
    if content_parts:
        if rule.title in content_parts[0]:
            content = " ".join(content_parts).strip()
        else:
            content = " ".join([rule.title, *content_parts]).strip()
    else:
        content = rule.title

    return {
        "platform": "video_channel",
        "rule_id": f"{spec.rule_id_prefix}{slugify_rule_code(rule.rule_code)}",
        "title": f"{rule.section_title}：{rule.title}",
        "content": content,
        "source_url": build_source_url(spec, rule),
        "severity": spec.section_severity.get(rule.section_code, "medium"),
        "tags": tags,
        "keywords": keywords,
        "regex_patterns": regex_patterns,
        "metadata": {
            "source_type": spec.source_type,
            "source_page_title": spec.title,
            "section_code": rule.section_code,
            "section_title": rule.section_title,
            "official_rule_code": rule.rule_code,
            "inferred_candidate_tags": inferred_tags,
            "source_urls": [spec.url],
            "image_assets": [
                {
                    "caption": asset.caption,
                    "path": asset.local_path,
                    "remote_url": asset.remote_url,
                }
                for asset in rule.images
            ],
            "video_case_links": rule.video_links,
            "reference_links": dedupe_preserve(rule.references),
        },
    }


def build_catalog(extractions: list[SourceExtraction]) -> dict[str, object]:
    total_rules = sum(len(extraction.rules) for extraction in extractions)
    total_images = sum(len(extraction.image_map) for extraction in extractions)
    return {
        "platform": "video_channel",
        "version": datetime.now().strftime("%Y-%m-%d"),
        "status": "ready",
        "title": "视频号内容规则库",
        "scope": "视频号官方《微信视频号运营规范》与《视频号常见违规内容概览》的本地化规则库",
        "intro": "整合视频号官方运营规范和常见违规内容概览，按条款编号拆解为可本地检索的内容规则。",
        "rule_count": total_rules,
        "image_count": total_images,
        "source_notes": [
            {
                "type": "official_rule_page",
                "title": extraction.spec.title,
                "url": extraction.spec.url,
                "local_archive": str(extraction.spec.archive_dir.relative_to(ROOT)),
            }
            for extraction in extractions
        ],
        "page_summaries": [
            {
                "source_type": extraction.spec.source_type,
                "title": extraction.spec.title,
                "intro": extraction.intro,
                "rule_count": len(extraction.rules),
                "image_count": len(extraction.image_map),
            }
            for extraction in extractions
        ],
        "categories": [
            {
                "source_type": extraction.spec.source_type,
                "source_title": extraction.spec.title,
                "section_code": section.section_code,
                "category": section.title,
                "rule_count": len([rule for rule in section.rules if should_include_rule(extraction.spec, rule)]),
                "sample_titles": [rule.title for rule in section.rules[:8]],
                "notes": section.notes[:3],
            }
            for extraction in extractions
            for section in extraction.sections
        ],
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def serialize_tokens(tokens: list[Token]) -> list[dict[str, object]]:
    return [
        {
            "kind": token.kind,
            "text": token.text,
            "src": token.src,
            "links": token.links,
        }
        for token in tokens
    ]


def serialize_sections(sections: list[Section]) -> dict[str, object]:
    return {
        "sections": [
            {
                "section_code": section.section_code,
                "title": section.title,
                "notes": section.notes,
                "rules": [
                    {
                        "rule_code": rule.rule_code,
                        "title": rule.title,
                        "body": rule.body,
                        "images": [
                            {
                                "caption": asset.caption,
                                "remote_url": asset.remote_url,
                                "local_path": asset.local_path,
                            }
                            for asset in rule.images
                        ],
                        "video_links": rule.video_links,
                        "references": dedupe_preserve(rule.references),
                    }
                    for rule in section.rules
                ],
            }
            for section in sections
        ]
    }


def extract_source(spec: SourceSpec) -> SourceExtraction:
    spec.archive_dir.mkdir(parents=True, exist_ok=True)
    html_text = fetch_html(spec)
    spec.raw_html_path.parent.mkdir(parents=True, exist_ok=True)
    spec.raw_html_path.write_text(html_text, encoding="utf-8")

    tokens = parse_tokens(html_text)
    write_json(spec.tokens_path, serialize_tokens(tokens))

    intro, sections = build_sections(spec, tokens)
    image_map = resolve_local_images(spec, sections)
    spec.local_html_path.write_text(build_local_html(spec, html_text, image_map), encoding="utf-8")

    structured_payload = {"intro": intro, **serialize_sections(sections)}
    write_json(spec.structured_path, structured_payload)

    rules = [
        build_rule_payload(spec, rule)
        for section in sections
        for rule in section.rules
        if should_include_rule(spec, rule)
    ]

    write_json(
        spec.archive_manifest_path,
        {
            "source_title": spec.title,
            "source_url": spec.url,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "html_path": str(spec.raw_html_path.relative_to(ROOT)),
            "local_html_path": str(spec.local_html_path.relative_to(ROOT)),
            "token_path": str(spec.tokens_path.relative_to(ROOT)),
            "structured_path": str(spec.structured_path.relative_to(ROOT)),
            "image_count": len(image_map),
            "rule_count": len(rules),
            "sections": [
                {
                    "section_code": section.section_code,
                    "title": section.title,
                    "rule_count": len([rule for rule in section.rules if should_include_rule(spec, rule)]),
                }
                for section in sections
            ],
        },
    )

    return SourceExtraction(spec=spec, intro=intro, sections=sections, image_map=image_map, rules=rules)


def main() -> None:
    extractions = [extract_source(spec) for spec in SOURCE_SPECS]
    rules = [rule for extraction in extractions for rule in extraction.rules]

    write_json(RULES_PATH, {"rules": rules})
    write_json(CATALOG_PATH, build_catalog(extractions))

    print(
        json.dumps(
            {
                "rules_path": str(RULES_PATH),
                "catalog_path": str(CATALOG_PATH),
                "source_archives": [str(extraction.spec.archive_dir) for extraction in extractions],
                "rule_count": len(rules),
                "image_count": sum(len(extraction.image_map) for extraction in extractions),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
