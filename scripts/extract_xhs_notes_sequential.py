from __future__ import annotations

import argparse
import json
import os
import re
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract Xiaohongshu note contents sequentially from a saved links list."
    )
    parser.add_argument("--links-file", required=True, help="JSON file containing note URLs in order.")
    parser.add_argument(
        "--cookie-string",
        default=os.environ.get("XHS_COOKIE_STRING", ""),
        help="Cookie string used when fetching note pages. Defaults to XHS_COOKIE_STRING.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Defaults to a timestamped directory under data/source_archives/xiaohongshu_rule_baike.",
    )
    parser.add_argument("--start-index", type=int, default=1, help="1-based start index in the links list.")
    parser.add_argument("--end-index", type=int, default=0, help="1-based end index in the links list. 0 means all.")
    return parser


def resolve_output_dir(output_dir: str) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(__file__).resolve().parent.parent / "data" / "source_archives" / "xiaohongshu_rule_baike"
    return (base / f"sequential_content_capture_{timestamp}").resolve()


def fetch_bytes(url: str, cookie_string: str, timeout: int = 30) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if cookie_string:
        headers["Cookie"] = cookie_string
    request = Request(url, headers=headers)
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        return response.read()


def fetch_text(url: str, cookie_string: str, timeout: int = 30) -> str:
    return fetch_bytes(url, cookie_string=cookie_string, timeout=timeout).decode("utf-8", errors="ignore")


def extract_state_expression(html: str) -> str:
    match = re.search(r"window\.__INITIAL_STATE__=(.*?)</script>", html, re.S)
    if not match:
        raise ValueError("window.__INITIAL_STATE__ not found")
    return match.group(1)


def parse_state(expr: str) -> dict[str, Any]:
    # The note page payload is almost JSON, only `undefined` needs normalization.
    sanitized = re.sub(r"\bundefined\b", "null", expr)
    return json.loads(sanitized)


def image_url_from_item(image: dict[str, Any]) -> str:
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


def note_payload_from_state(state: dict[str, Any]) -> dict[str, Any]:
    note_state = state.get("note", {})
    detail_map = note_state.get("noteDetailMap") or note_state.get("note_detail_map") or {}
    if not detail_map:
        raise ValueError("noteDetailMap missing")
    first_key = next(iter(detail_map.keys()))
    payload = detail_map[first_key]
    note = payload.get("note") if isinstance(payload, dict) else None
    if not isinstance(note, dict):
        raise ValueError("note payload missing")
    return note


def normalize_note(
    index: int,
    url: str,
    note: dict[str, Any],
    html_path: Path,
    image_paths: list[str],
) -> dict[str, Any]:
    user = note.get("user") or {}
    tag_list = note.get("tagList") or note.get("tag_list") or []
    note_id = note.get("noteId") or note.get("note_id") or url.rstrip("/").split("/")[-1]
    return {
        "index": index,
        "note_id": note_id,
        "note_url": url,
        "title": note.get("title") or "",
        "desc": note.get("desc") or note.get("description") or "",
        "nickname": user.get("nickname") or user.get("nickName") or user.get("nick_name") or "",
        "user_id": user.get("userId") or user.get("user_id") or "",
        "published_time": note.get("time"),
        "note_type": note.get("type") or "",
        "tags": [tag.get("name") for tag in tag_list if isinstance(tag, dict) and tag.get("name")],
        "image_count": len(note.get("imageList") or []),
        "images": image_paths,
        "html_path": str(html_path),
    }


def main() -> int:
    args = build_parser().parse_args()
    if not args.cookie_string:
        raise SystemExit("cookie string is required, pass --cookie-string or set XHS_COOKIE_STRING")

    links = json.loads(Path(args.links_file).expanduser().read_text(encoding="utf-8"))
    start = max(1, args.start_index)
    end = args.end_index if args.end_index > 0 else len(links)
    selected = list(enumerate(links[start - 1 : end], start=start))

    output_dir = resolve_output_dir(args.output_dir)
    html_dir = output_dir / "html"
    notes_dir = output_dir / "notes"
    images_dir = output_dir / "images"
    for path in (output_dir, html_dir, notes_dir, images_dir):
        path.mkdir(parents=True, exist_ok=True)

    notes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, url in selected:
        print(f"[extract] {index}/{len(links)} {url}", flush=True)
        try:
            html = fetch_text(url, cookie_string=args.cookie_string, timeout=30)
            expr = extract_state_expression(html)
            state = parse_state(expr)
            note = note_payload_from_state(state)
            note_id = note.get("noteId") or note.get("note_id") or url.rstrip("/").split("/")[-1]

            html_path = html_dir / f"{index:03d}_{note_id}.html"
            html_path.write_text(html, encoding="utf-8")

            image_paths: list[str] = []
            note_image_dir = images_dir / f"{index:03d}_{note_id}"
            note_image_dir.mkdir(parents=True, exist_ok=True)
            for image_index, image in enumerate(note.get("imageList") or [], start=1):
                image_url = image_url_from_item(image)
                if not image_url:
                    continue
                image_path = note_image_dir / f"{image_index:02d}{guess_extension(image_url)}"
                if not image_path.exists():
                    image_path.write_bytes(fetch_bytes(image_url, cookie_string=args.cookie_string, timeout=30))
                image_paths.append(str(image_path))

            normalized = normalize_note(index=index, url=url, note=note, html_path=html_path, image_paths=image_paths)
            note_path = notes_dir / f"{index:03d}_{note_id}.json"
            note_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
            notes.append(normalized)
            print(f"[success] {index:03d} {normalized['title']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failures.append({"index": index, "url": url, "error": str(exc)})
            print(f"[failure] {index:03d} {url} {exc}", flush=True)

    manifest = {
        "source": "xiaohongshu_note_html_fetch",
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "links_file": str(Path(args.links_file).expanduser().resolve()),
        "start_index": start,
        "end_index": end,
        "note_count": len(notes),
        "failure_count": len(failures),
        "notes_path": str(notes_dir),
        "images_path": str(images_dir),
        "failures": failures,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "notes_index.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
