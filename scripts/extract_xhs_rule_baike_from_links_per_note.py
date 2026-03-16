from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Xiaohongshu notes from a prepared links file with a fresh browser session per note."
    )
    parser.add_argument(
        "--links-file",
        required=True,
        help="JSON file containing Xiaohongshu note URLs.",
    )
    parser.add_argument(
        "--mediacrawler-path",
        default="/tmp/MediaCrawler",
        help="Path to the cloned MediaCrawler repository.",
    )
    parser.add_argument(
        "--cookie-string",
        default=os.environ.get("XHS_COOKIE_STRING", ""),
        help="Cookie string used for cookie login. Defaults to XHS_COOKIE_STRING.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Defaults to a timestamped archive directory.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional note limit. 0 means all links in the file.",
    )
    return parser.parse_args()


def ensure_mediacrawler_imports(repo_path: Path) -> None:
    if not repo_path.exists():
        raise FileNotFoundError(f"MediaCrawler path not found: {repo_path}")
    if str(repo_path) not in sys.path:
        sys.path.insert(0, str(repo_path))


def resolve_output_dir(output_dir: str) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(__file__).resolve().parent.parent / "data" / "source_archives" / "xiaohongshu_rule_baike"
    return (base / f"per_note_capture_{timestamp}").resolve()


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
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".mp4"}:
        return suffix
    if "webp" in url:
        return ".webp"
    return ".bin"


def classify_note(title: str, desc: str) -> str:
    text = f"{title}\n{desc}"
    rules = [
        ("社区公约与总则", ("社区公约", "公约", "规则百科薯转播", "约法三章")),
        ("AI 内容治理", ("AI", "AIGC", "深度合成", "生成式")),
        ("未成年人保护", ("未成年", "青少年", "学生抽烟")),
        ("导流与私下交易", ("导流", "引流", "站外", "加微信", "加群")),
        ("广告与营销治理", ("广告", "营销", "商单", "种草", "带货")),
        ("虚假内容与人设", ("虚假", "人设", "摆拍", "造假", "夸张")),
        ("医疗健康与医美", ("医疗", "医美", "偏方", "医院")),
        ("低俗色情与不雅行为", ("低俗", "色情", "不雅", "擦边")),
        ("恶意竞争与黑灰产", ("恶意竞争", "黑灰产", "矩阵号", "水军", "刷量")),
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


async def inject_cookie_login(browser_context: Any, page: Any, cookie_string: str) -> None:
    from media_platform.xhs.login import XiaoHongShuLogin

    login = XiaoHongShuLogin(
        login_type="cookie",
        browser_context=browser_context,
        context_page=page,
        cookie_str=cookie_string,
    )
    await login.login_by_cookies()


async def extract_note_state(page: Any, note_url: str) -> dict[str, Any]:
    await page.goto(note_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(5000)
    return await page.evaluate("() => window.__INITIAL_STATE__ || null")


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


async def download_file(client: httpx.AsyncClient, url: str, destination: Path) -> None:
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    destination.write_bytes(response.content)


async def extract_one_note(
    note_url: str,
    cookie_string: str,
    raw_dir: Path,
    notes_dir: Path,
    images_dir: Path,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    import config
    from media_platform.xhs.core import XiaoHongShuCrawler

    config.ENABLE_CDP_MODE = True
    config.CDP_HEADLESS = False
    config.SAVE_LOGIN_STATE = True
    config.PLATFORM = "xhs"

    crawler = XiaoHongShuCrawler()
    async with async_playwright() as playwright:
        crawler.browser_context = await crawler.launch_browser_with_cdp(
            playwright,
            None,
            crawler.user_agent,
            headless=config.CDP_HEADLESS,
        )
        page = await crawler.browser_context.new_page()
        await page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
        await inject_cookie_login(crawler.browser_context, page, cookie_string)
        state = await extract_note_state(page, note_url)
        note = note_from_state(state or {})
        if not note:
            raise ValueError("note state missing noteDetailMap payload")

        note_id = note.get("noteId") or note.get("note_id") or note_url.rstrip("/").split("/")[-1]
        raw_path = raw_dir / f"{note_id}.json"
        raw_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        image_paths: list[str] = []
        note_image_dir = images_dir / note_id
        note_image_dir.mkdir(parents=True, exist_ok=True)
        for image_index, image in enumerate(note.get("imageList") or note.get("image_list") or [], start=1):
            image_url = normalize_image_url(image)
            if not image_url:
                continue
            image_path = note_image_dir / f"{image_index:02d}{guess_extension(image_url)}"
            if not image_path.exists():
                await download_file(client, image_url, image_path)
            image_paths.append(str(image_path))

        normalized = normalize_note(note_url, note, image_paths)
        normalized["raw_path"] = str(raw_path)
        (notes_dir / f"{note_id}.json").write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if getattr(crawler, "cdp_manager", None):
            await crawler.cdp_manager.cleanup(force=True)
        return normalized


async def main_async(args: argparse.Namespace) -> Path:
    links = json.loads(Path(args.links_file).expanduser().read_text(encoding="utf-8"))
    if args.limit:
        links = links[: args.limit]

    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "notes_raw"
    notes_dir = output_dir / "notes"
    images_dir = output_dir / "images"
    category_dir = output_dir / "categories"
    for path in (raw_dir, notes_dir, images_dir, category_dir):
        path.mkdir(parents=True, exist_ok=True)

    (output_dir / "profile_links.json").write_text(
        json.dumps(links, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    notes: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        for index, note_url in enumerate(links, start=1):
            print(f"[extract] {index}/{len(links)} {note_url}", flush=True)
            try:
                normalized = await extract_one_note(
                    note_url=note_url,
                    cookie_string=args.cookie_string,
                    raw_dir=raw_dir,
                    notes_dir=notes_dir,
                    images_dir=images_dir,
                    client=client,
                )
                normalized["index"] = index
                notes.append(normalized)
                print(
                    f"[success] {normalized['note_id']} images={normalized['image_count']} title={normalized['title']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append({"url": note_url, "error": str(exc)})
                print(f"[failure] {note_url} {exc}", flush=True)

    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in notes:
        categories[note["category"]].append(note)

    for category, items in categories.items():
        (category_dir / f"{slugify(category)}.json").write_text(
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
        "source": "xiaohongshu_rule_baike_per_note",
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "note_count": len(notes),
        "failure_count": len(failures),
        "categories": {category: len(items) for category, items in categories.items()},
        "links_file": str(Path(args.links_file).expanduser().resolve()),
        "notes_path": str(notes_dir),
        "images_path": str(images_dir),
        "failures": failures,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "notes_index.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir


def main() -> int:
    args = parse_args()
    if not args.cookie_string:
        raise SystemExit("cookie string is required")
    ensure_mediacrawler_imports(Path(args.mediacrawler_path).expanduser().resolve())
    output_dir = asyncio.run(main_async(args))
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
