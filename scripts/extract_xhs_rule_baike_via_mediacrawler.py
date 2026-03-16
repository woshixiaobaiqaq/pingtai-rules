from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

DEFAULT_PROFILE_URL = (
    "https://www.xiaohongshu.com/user/profile/"
    "677e62aa000000000801e7c3"
    "?xsec_token=ABnC9jbizZnxmtD13N9ja3Ea2ePhpgLRfwoIYXf5ihWFU%3D"
    "&xsec_source=pc_search"
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract Xiaohongshu rule notes via MediaCrawler browser context."
    )
    parser.add_argument(
        "--mediacrawler-path",
        default="/tmp/MediaCrawler",
        help="Path to the cloned MediaCrawler repository.",
    )
    parser.add_argument(
        "--profile-url",
        default=DEFAULT_PROFILE_URL,
        help="Creator profile URL.",
    )
    parser.add_argument(
        "--cookie-string",
        default=os.environ.get("XHS_COOKIE_STRING", ""),
        help="Cookie string used for cookie login. Defaults to XHS_COOKIE_STRING.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Defaults to a timestamped directory under data/source_archives/xiaohongshu_rule_baike.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional note limit. 0 means no explicit limit.",
    )
    return parser


def ensure_mediacrawler_imports(repo_path: Path) -> None:
    if not repo_path.exists():
        raise FileNotFoundError(f"MediaCrawler path not found: {repo_path}")
    if str(repo_path) not in sys.path:
        sys.path.insert(0, str(repo_path))


def slugify(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", name).strip("-")
    return cleaned or "uncategorized"


def normalize_image_url(image: dict[str, Any]) -> str:
    for key in ("urlDefault", "urlPre", "url"):
        value = image.get(key)
        if value:
            return value.replace("http://", "https://")
    for item in image.get("infoList", []):
        value = item.get("url")
        if value:
            return value.replace("http://", "https://")
    return ""


def guess_extension(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".mp4"}:
        return suffix
    if "!nd_" in path or "webp" in path:
        return ".webp"
    return ".bin"


def classify_note(title: str, desc: str) -> str:
    text = f"{title}\n{desc}"
    rules = [
        ("社区公约与总则", ("社区公约", "公约", "规则百科薯转播", "约法三章")),
        ("AI 内容治理", ("AI", "AIGC", "深度合成", "生成式", "模型")),
        ("未成年人保护", ("未成年", "青少年", "学生抽烟", "校园霸凌")),
        ("导流与私下交易", ("导流", "引流", "私下交易", "站外", "加微信", "加群")),
        ("广告与营销治理", ("广告", "营销", "商单", "种草", "带货", "合作")),
        ("虚假内容与人设", ("虚假", "人设", "摆拍", "造假", "夸张", "标题党")),
        ("医疗健康与医美", ("医疗", "医美", "治愈", "偏方", "医生", "医院")),
        ("低俗色情与不雅行为", ("低俗", "色情", "不雅", "擦边", "软色情")),
        ("恶意竞争与黑灰产", ("恶意竞争", "黑灰产", "矩阵号", "水军", "刷量", "攻击")),
    ]
    for category, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category
    return "其他规则"


def note_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    note_state = state.get("note", {})
    detail_map = note_state.get("noteDetailMap") or note_state.get("note_detail_map") or {}
    if not detail_map:
        return None
    first_key = next(iter(detail_map.keys()))
    payload = detail_map[first_key]
    note = payload.get("note") if isinstance(payload, dict) else None
    if isinstance(note, dict):
        return note
    if isinstance(payload, dict):
        return payload
    return None


@dataclass
class ExtractionContext:
    cookie_string: str
    profile_url: str
    output_dir: Path
    limit: int
    mediacrawler_path: Path


async def inject_cookie_login(browser_context: Any, page: Any, cookie_string: str) -> None:
    from media_platform.xhs.login import XiaoHongShuLogin

    login = XiaoHongShuLogin(
        login_type="cookie",
        browser_context=browser_context,
        context_page=page,
        cookie_str=cookie_string,
    )
    await login.login_by_cookies()


async def extract_profile_links(page: Any, profile_url: str, limit: int) -> list[str]:
    await page.goto(profile_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    hrefs = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href*="/explore/"]'))
          .map((a) => a.href)
        """
    )
    collected: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        if href and href not in seen:
            seen.add(href)
            collected.append(href)
    return collected[:limit] if limit else collected


async def extract_note_state(page: Any, note_url: str) -> dict[str, Any]:
    await page.goto(note_url, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_function(
            """
            () => {
              const state = window.__INITIAL_STATE__;
              const note = state && state.note;
              const detailMap = note && (note.noteDetailMap || note.note_detail_map);
              return !!detailMap && Object.keys(detailMap).length > 0;
            }
            """,
            timeout=10_000,
        )
    except Exception:  # noqa: BLE001
        await page.wait_for_timeout(5000)
    return await page.evaluate("() => window.__INITIAL_STATE__ || null")


async def download_file(client: httpx.AsyncClient, url: str, destination: Path) -> None:
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    destination.write_bytes(response.content)


def normalize_note(note_url: str, note: dict[str, Any], image_paths: list[str]) -> dict[str, Any]:
    note_id = note.get("noteId") or note.get("note_id") or note_url.rstrip("/").split("/")[-1]
    title = (note.get("title") or "").strip()
    desc = (note.get("desc") or note.get("description") or "").strip()
    user = note.get("user") or {}
    image_list = note.get("imageList") or note.get("image_list") or []
    tag_list = note.get("tagList") or note.get("tag_list") or []

    return {
        "note_id": note_id,
        "note_url": note_url,
        "title": title,
        "desc": desc,
        "nickname": user.get("nickname") or user.get("nickName") or user.get("nick_name") or "",
        "user_id": user.get("userId") or user.get("user_id") or "",
        "published_time": note.get("time") or "",
        "note_type": note.get("type") or "",
        "tags": [tag.get("name") for tag in tag_list if isinstance(tag, dict) and tag.get("name")],
        "image_count": len(image_list),
        "images": image_paths,
        "category": classify_note(title, desc),
    }


async def run_extraction(ctx: ExtractionContext) -> None:
    import config
    from media_platform.xhs.core import XiaoHongShuCrawler

    config.ENABLE_CDP_MODE = True
    config.CDP_HEADLESS = False
    config.SAVE_LOGIN_STATE = True
    config.PLATFORM = "xhs"

    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = ctx.output_dir / "notes_raw"
    normalized_dir = ctx.output_dir / "notes"
    images_dir = ctx.output_dir / "images"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    crawler = XiaoHongShuCrawler()
    async with async_playwright() as playwright:
        crawler.browser_context = await crawler.launch_browser_with_cdp(
            playwright,
            None,
            crawler.user_agent,
            headless=config.CDP_HEADLESS,
        )
        profile_page = await crawler.browser_context.new_page()
        await profile_page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
        await inject_cookie_login(crawler.browser_context, profile_page, ctx.cookie_string)

        profile_links = await extract_profile_links(profile_page, ctx.profile_url, ctx.limit)
        (ctx.output_dir / "profile_links.json").write_text(
            json.dumps(profile_links, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        notes: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        note_page = await crawler.browser_context.new_page()
        await note_page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")

        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            for index, note_url in enumerate(profile_links, start=1):
                try:
                    print(f"[extract] {index}/{len(profile_links)} {note_url}", flush=True)
                    state = await extract_note_state(note_page, note_url)
                    note = note_from_state(state or {})
                    if not note:
                        raise ValueError("note state missing noteDetailMap payload")

                    note_id = note.get("noteId") or note.get("note_id") or note_url.rstrip("/").split("/")[-1]
                    raw_path = raw_dir / f"{note_id}.json"
                    raw_path.write_text(
                        json.dumps(state, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                    image_list = note.get("imageList") or note.get("image_list") or []
                    image_paths: list[str] = []
                    note_image_dir = images_dir / note_id
                    note_image_dir.mkdir(parents=True, exist_ok=True)
                    for image_index, image in enumerate(image_list, start=1):
                        image_url = normalize_image_url(image)
                        if not image_url:
                            continue
                        extension = guess_extension(image_url)
                        image_path = note_image_dir / f"{image_index:02d}{extension}"
                        if not image_path.exists():
                            await download_file(client, image_url, image_path)
                        image_paths.append(str(image_path))

                    normalized = normalize_note(note_url, note, image_paths)
                    normalized["index"] = index
                    normalized["raw_path"] = str(raw_path)
                    normalized_path = normalized_dir / f"{note_id}.json"
                    normalized_path.write_text(
                        json.dumps(normalized, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    notes.append(normalized)
                    print(
                        f"[success] {note_id} images={len(image_paths)} title={normalized['title']}",
                        flush=True,
                    )
                    await note_page.wait_for_timeout(1200)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"url": note_url, "error": str(exc)})
                    print(f"[failure] {note_url} {exc}", flush=True)
                    await note_page.wait_for_timeout(1500)

        categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for note in notes:
            categories[note["category"]].append(note)

        category_dir = ctx.output_dir / "categories"
        category_dir.mkdir(parents=True, exist_ok=True)
        for category, items in categories.items():
            category_path = category_dir / f"{slugify(category)}.json"
            category_path.write_text(
                json.dumps(
                    {
                        "category": category,
                        "note_count": len(items),
                        "notes": items,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        manifest = {
            "source": "xiaohongshu_rule_baike_via_mediacrawler",
            "profile_url": ctx.profile_url,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "note_count": len(notes),
            "failure_count": len(failures),
            "categories": {category: len(items) for category, items in categories.items()},
            "notes_path": str(normalized_dir),
            "images_path": str(images_dir),
            "failures": failures,
        }
        (ctx.output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (ctx.output_dir / "notes_index.json").write_text(
            json.dumps(notes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if getattr(crawler, "cdp_manager", None):
            await crawler.cdp_manager.cleanup(force=True)


def resolve_output_dir(output_dir: str) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(__file__).resolve().parent.parent / "data" / "source_archives" / "xiaohongshu_rule_baike"
    return (base / f"mediacrawler_capture_{timestamp}").resolve()


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.cookie_string:
        parser.error("--cookie-string is required or set XHS_COOKIE_STRING")

    mediacrawler_path = Path(args.mediacrawler_path).expanduser().resolve()
    ensure_mediacrawler_imports(mediacrawler_path)

    output_dir = resolve_output_dir(args.output_dir)
    ctx = ExtractionContext(
        cookie_string=args.cookie_string,
        profile_url=args.profile_url,
        output_dir=output_dir,
        limit=args.limit,
        mediacrawler_path=mediacrawler_path,
    )
    asyncio.run(run_extraction(ctx))
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
