from __future__ import annotations

import argparse
import html
import http.client
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_PAGE_URL = (
    "https://aweme.snssdk.com/falcon/fe_douyin_security_react/rule/platform_norm/"
    "?enter_from=share_qrcode&hide_nav_bar=1"
    "&iid=MS4wLjABAAAAMBKji6p88_6A9AkMHMCHOLnturxSxzM4KRNKmyV9ngHjn5qvCnauXD2ozOKKrq6A"
    "&page_type=rule_explain&schema_type=11&timestamp=1773213833"
    "&u_code=42limiab882a"
    "&did=MS4wLjABAAAASx3x5XHIbJ__xzBuyA6UO1qvpfa1wwaXFsiQWeJVkq2tIOXzjk7Lv0YIA9nPb6il"
    "&ug_share_id=6f968de2110ea_1773213834354"
)
MANIFEST_URL = "https://lf3-beecdn.bytetos.com/obj/ies-fe-bee/bee_prod/biz_1107/bee_prod_1107_bee_publish_12362.json"
DETAIL_BEE_URL = "https://lf3-beecdn.bytetos.com/obj/ies-fe-bee/bee_prod/biz_1107/bee_prod_1107_bee_publish_12334.json"
ARTICLE_DETAIL_URL = "https://school.jinritemai.com/api/eschool/v2/library/article/detail?id={commerce_id}"
DETAIL_SHELL_URL = (
    "https://api.amemv.com/falcon/fe_douyin_security_react/rule/norm_content/?hide_nav_bar=1&commerce_id={commerce_id}"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)


@dataclass(slots=True)
class ArticleArchive:
    title: str
    commerce_id: str
    source_url: str
    article_json_path: str
    detail_shell_path: str
    rendered_html_path: str
    image_paths: list[str]


def fetch_text(url: str) -> str:
    return fetch_url(url).decode("utf-8")


def fetch_bytes(url: str) -> bytes:
    return fetch_url(url)


def fetch_url(url: str, *, retries: int = 4, timeout: int = 120) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except (ConnectionResetError, TimeoutError, URLError, http.client.RemoteDisconnected) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(attempt)
    assert last_error is not None
    raise last_error


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_-]+", "_", value).strip("_")
    return slug or "item"


def collect_table_images(deltas: dict[str, Any], zone_ref: str, seen: set[str] | None = None) -> list[str]:
    seen = seen or set()
    urls: list[str] = []
    for zone_id in zone_ref.split():
        if zone_id in seen or zone_id not in deltas:
            continue
        seen.add(zone_id)
        for op in deltas[zone_id].get("ops", []):
            attrs = op.get("attributes", {})
            if attrs.get("IMAGE") == "true" and attrs.get("fileSrc"):
                urls.append(attrs["fileSrc"])
            if "aceTable" in attrs:
                urls.extend(collect_table_images(deltas, attrs["aceTable"], seen))
            inserted = op.get("insert")
            if isinstance(inserted, dict) and "id" in inserted:
                urls.extend(collect_table_images(deltas, inserted["id"], seen))
    return urls


def extract_all_image_urls(content_data: dict[str, Any]) -> list[str]:
    deltas = content_data["deltas"]
    urls = [
        attachment["url"] for attachment in content_data.get("attachments", []) if attachment.get("type") == "image"
    ]

    for op in deltas["0"].get("ops", []):
        attrs = op.get("attributes", {})
        if attrs.get("IMAGE") == "true" and attrs.get("fileSrc"):
            urls.append(attrs["fileSrc"])
        if "aceTable" in attrs:
            urls.extend(collect_table_images(deltas, attrs["aceTable"]))

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def format_inline(text: str, attrs: dict[str, Any]) -> str:
    escaped = html.escape(text)
    if attrs.get("bold") == "true":
        escaped = f"<strong>{escaped}</strong>"
    return escaped


def render_ops_to_html(content_data: dict[str, Any], image_map: dict[str, str]) -> str:
    deltas = content_data["deltas"]
    root_ops = deltas["0"]["ops"]
    lines: list[str] = []
    current_fragments: list[str] = []
    pending_block: dict[str, Any] = {}
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            lines.append("</ul>")
            in_list = False

    def emit_image(url: str, extra_class: str = "") -> None:
        local_src = image_map.get(url, url)
        lines.append(
            f'<figure class="rule-image {extra_class}"><img src="{html.escape(local_src)}" alt="rule image"></figure>'
        )

    def flush_line() -> None:
        nonlocal current_fragments, pending_block, in_list
        if not current_fragments:
            pending_block = {}
            return
        body = "".join(current_fragments).strip()
        current_fragments = []
        if not body:
            pending_block = {}
            return

        block_type = "paragraph"
        if pending_block.get("blockquote") == "true":
            close_list()
            lines.append(f"<blockquote><p>{body}</p></blockquote>")
        elif pending_block.get("list"):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{body}</li>")
        elif pending_block.get("heading") == "h3":
            close_list()
            lines.append(f"<h2>{body}</h2>")
        else:
            close_list()
            plain_text = re.sub(r"<[^>]+>", "", body)
            if len(plain_text) <= 12 and "<strong>" in body:
                block_type = "heading"
            if block_type == "heading":
                lines.append(f"<h3>{body}</h3>")
            else:
                lines.append(f"<p>{body}</p>")
        pending_block = {}

    for op in root_ops:
        attrs = op.get("attributes", {})
        inserted = op.get("insert")

        if inserted == "*" and attrs.get("lmkr") == "1":
            if any(key in attrs for key in ("heading", "list", "blockquote")):
                pending_block = attrs
            continue

        if attrs.get("IMAGE") == "true" and attrs.get("fileSrc"):
            flush_line()
            emit_image(attrs["fileSrc"])
            continue

        if "aceTable" in attrs:
            flush_line()
            for url in collect_table_images(deltas, attrs["aceTable"]):
                emit_image(url, "table-image")
            continue

        if isinstance(inserted, dict):
            continue

        if not isinstance(inserted, str):
            continue

        parts = inserted.split("\n")
        for index, part in enumerate(parts):
            if part:
                current_fragments.append(format_inline(part, attrs))
            if index < len(parts) - 1:
                flush_line()

    flush_line()
    close_list()
    return "\n".join(lines)


def render_article_page(
    *,
    title: str,
    commerce_id: str,
    overview: str,
    image_count: int,
    body_html: str,
    source_url: str,
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - 抖音规则本地归档</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f3ee;
      --card: #fffdf9;
      --ink: #1e2430;
      --muted: #627089;
      --accent: #d95d39;
      --border: #e7ddd1;
    }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Noto Sans SC", sans-serif;
      background: radial-gradient(circle at top left, #fff7ef, var(--bg) 40%);
      color: var(--ink);
      line-height: 1.7;
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 24px 80px;
    }}
    .hero, .content {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: 0 14px 40px rgba(32, 26, 20, 0.06);
    }}
    .hero {{
      padding: 28px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 8px 0 12px;
      font-size: 34px;
      line-height: 1.2;
    }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
    }}
    .overview {{
      margin-top: 16px;
      font-size: 16px;
    }}
    .content {{
      padding: 28px;
    }}
    h2 {{
      margin: 32px 0 12px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
      font-size: 26px;
    }}
    h3 {{
      margin: 24px 0 10px;
      color: #41506a;
      font-size: 19px;
    }}
    p, li {{
      font-size: 16px;
    }}
    blockquote {{
      margin: 14px 0;
      padding: 8px 18px;
      border-left: 4px solid #a6c48a;
      background: #f4faef;
      border-radius: 6px;
    }}
    ul {{
      margin: 12px 0 18px 20px;
      padding: 0;
    }}
    .rule-image {{
      margin: 18px 0;
      padding: 12px;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 14px;
    }}
    .rule-image img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
      border-radius: 10px;
    }}
    .footer-note {{
      margin-top: 28px;
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="eyebrow">Douyin Rule Archive</div>
      <h1>{html.escape(title)}</h1>
      <div class="meta">commerce_id: {html.escape(commerce_id)} | 本地图片数: {image_count}</div>
      <div class="overview">{html.escape(overview)}</div>
      <div class="footer-note">线上来源: <a href="{html.escape(source_url)}">{html.escape(source_url)}</a></div>
    </section>
    <section class="content">
      {body_html}
    </section>
  </main>
</body>
</html>
"""


def render_index_page(articles: list[ArticleArchive], source_page_path: str, manifest_path: str) -> str:
    items = "\n".join(
        f"""
        <article class="card">
          <h2><a href="{html.escape(article.rendered_html_path)}">{html.escape(article.title)}</a></h2>
          <div class="meta">commerce_id: {html.escape(article.commerce_id)} | 图片 {len(article.image_paths)} 张</div>
          <div class="links">
            <a href="{html.escape(article.rendered_html_path)}">离线阅读页</a>
            <a href="{html.escape(article.article_json_path)}">原始 JSON</a>
            <a href="{html.escape(article.detail_shell_path)}">详情页壳 HTML</a>
            <a href="{html.escape(article.source_url)}">线上详情页</a>
          </div>
        </article>
        """
        for article in articles
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>抖音规则解读本地归档</title>
  <style>
    body {{
      margin: 0;
      font-family: "PingFang SC", "Noto Sans SC", sans-serif;
      background: linear-gradient(180deg, #f4efe7 0%, #f9f7f3 100%);
      color: #1f2735;
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 36px 24px 80px;
    }}
    .hero {{
      margin-bottom: 24px;
      padding: 28px;
      background: #1f3552;
      color: #fff;
      border-radius: 20px;
    }}
    .hero p {{
      color: rgba(255, 255, 255, 0.82);
      line-height: 1.7;
    }}
    .hero a {{
      color: #ffd39f;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
    }}
    .card {{
      background: #fffdf9;
      border: 1px solid #e7ddd1;
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 12px 34px rgba(32, 26, 20, 0.05);
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 20px;
      line-height: 1.3;
    }}
    .card h2 a {{
      color: #23314a;
      text-decoration: none;
    }}
    .meta {{
      margin-bottom: 12px;
      color: #6a7688;
      font-size: 14px;
    }}
    .links {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .links a {{
      color: #b34d1e;
      text-decoration: none;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>抖音规则解读本地归档</h1>
      <p>
        该目录将入口页、Bee 配置、16 个规则详情 JSON、所有示例图片和离线阅读页统一保存到本地，
        方便核对线上规则与后续结构化处理。
      </p>
      <p>入口页壳文件：<a href="{html.escape(source_page_path)}">{html.escape(source_page_path)}</a></p>
      <p>目录 Bee 清单：<a href="{html.escape(manifest_path)}">{html.escape(manifest_path)}</a></p>
    </section>
    <section class="grid">
      {items}
    </section>
  </main>
</body>
</html>
"""


def archive_rules(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    article_dir = raw_dir / "articles"
    shell_dir = raw_dir / "detail_shells"
    image_dir = output_dir / "images"
    page_dir = output_dir / "pages"

    source_page_path = raw_dir / "source_page.html"
    manifest_path = raw_dir / "bee_publish_12362.json"
    detail_bee_path = raw_dir / "bee_publish_12334.json"

    if not source_page_path.exists():
        write_text(source_page_path, fetch_text(SOURCE_PAGE_URL))
    if not manifest_path.exists():
        write_text(manifest_path, fetch_text(MANIFEST_URL))
    if not detail_bee_path.exists():
        write_text(detail_bee_path, fetch_text(DETAIL_BEE_URL))

    manifest_text = manifest_path.read_text(encoding="utf-8")

    manifest = json.loads(manifest_text)
    categories = sorted(
        manifest["bee_dsrc_16158"],
        key=lambda item: item.get("order", 0),
        reverse=True,
    )

    archived_articles: list[ArticleArchive] = []
    combined_sections: list[str] = []

    for category in categories:
        title = category["title"]
        commerce_id = category["commerce_id"]
        source_url = DETAIL_SHELL_URL.format(commerce_id=commerce_id)
        print(f"Archiving {title} ({commerce_id})")

        article_path = article_dir / f"{commerce_id}.json"
        if not article_path.exists():
            article_text = fetch_text(ARTICLE_DETAIL_URL.format(commerce_id=commerce_id))
            write_text(article_path, article_text)
        else:
            article_text = article_path.read_text(encoding="utf-8")

        detail_shell_path = shell_dir / f"{commerce_id}.html"
        if not detail_shell_path.exists():
            write_text(detail_shell_path, fetch_text(source_url))

        article_payload = json.loads(article_text)
        article_info = article_payload["data"]["article_info"]
        content_data = json.loads(article_info["content"])

        local_image_paths: list[str] = []
        page_image_map: dict[str, str] = {}
        combined_image_map: dict[str, str] = {}
        image_urls = extract_all_image_urls(content_data)
        for index, remote_url in enumerate(image_urls, start=1):
            parsed_url = urlparse(remote_url)
            extension = Path(parsed_url.path).suffix or ".png"
            local_image = image_dir / commerce_id / f"{index:02d}_{slugify(Path(parsed_url.path).stem)}{extension}"
            if not local_image.exists():
                write_bytes(local_image, fetch_bytes(remote_url))
            relative_image = local_image.relative_to(output_dir).as_posix()
            local_image_paths.append(relative_image)
            page_image_map[remote_url] = "../" + relative_image
            combined_image_map[remote_url] = relative_image

        body_html = render_ops_to_html(content_data, page_image_map)
        combined_body_html = render_ops_to_html(content_data, combined_image_map)
        article_html = render_article_page(
            title=title,
            commerce_id=commerce_id,
            overview=article_info.get("description", ""),
            image_count=len(local_image_paths),
            body_html=body_html,
            source_url=source_url,
        )
        rendered_path = page_dir / f"{commerce_id}.html"
        write_text(rendered_path, article_html)

        archived_articles.append(
            ArticleArchive(
                title=title,
                commerce_id=commerce_id,
                source_url=source_url,
                article_json_path=article_path.relative_to(output_dir).as_posix(),
                detail_shell_path=detail_shell_path.relative_to(output_dir).as_posix(),
                rendered_html_path=rendered_path.relative_to(output_dir).as_posix(),
                image_paths=local_image_paths,
            )
        )

        combined_sections.append(
            f"<section><h2>{html.escape(title)}</h2>"
            f"<p>commerce_id: {html.escape(commerce_id)}</p>"
            f"{combined_body_html}</section>"
        )

    write_text(
        output_dir / "index.html",
        render_index_page(
            archived_articles,
            source_page_path.relative_to(output_dir).as_posix(),
            manifest_path.relative_to(output_dir).as_posix(),
        ),
    )
    write_text(
        output_dir / "all_rules.html",
        (
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>抖音规则解读全集</title>"
            "<style>"
            "body{margin:0 auto;max-width:1080px;padding:32px 24px 80px;"
            'font-family:"PingFang SC","Noto Sans SC",sans-serif;line-height:1.75;'
            "background:#faf7f2;color:#1f2735}"
            "section{margin-bottom:36px;padding:24px;border:1px solid #e7ddd1;"
            "border-radius:18px;background:#fffdf9}"
            ".rule-image{margin:16px 0;padding:12px;border:1px solid #e7ddd1;"
            "border-radius:14px;background:#fff}"
            ".rule-image img{display:block;max-width:100%;height:auto;margin:0 auto}"
            "blockquote{margin:14px 0;padding:8px 18px;border-left:4px solid #a6c48a;"
            "background:#f4faef;border-radius:6px}"
            "h2{font-size:28px}h3{color:#41506a}ul{margin-left:20px}"
            "</style></head><body>"
        )
        + "\n".join(combined_sections)
        + "</body></html>",
    )
    write_text(
        output_dir / "README.md",
        "\n".join(
            [
                "# Douyin Rule Explain Archive",
                "",
                "本目录保存了抖音规则解读页的本地归档版本，包括：",
                "",
                "- `raw/source_page.html`: 入口页原始 HTML",
                "- `raw/bee_publish_12362.json`: 规则目录 Bee 清单",
                "- `raw/bee_publish_12334.json`: 详情页 Bee 配置",
                "- `raw/articles/*.json`: 每个 `commerce_id` 的原始规则正文 JSON",
                "- `raw/detail_shells/*.html`: 每个规则详情页壳 HTML",
                "- `images/<commerce_id>/`: 下载到本地的示例图片",
                "- `pages/*.html`: 可离线浏览的单分类页面",
                "- `index.html`: 归档索引页",
                "- `all_rules.html`: 16 个分类拼接后的单页全集",
                "",
                (
                    "说明：离线阅读页来自文章 JSON 的结构化渲染，"
                    "原始 JSON 已同步保留，方便你后续继续校验或做更细粒度解析。"
                ),
            ]
        ),
    )
    write_text(
        output_dir / "archive_manifest.json",
        json.dumps(
            {
                "source_page_url": SOURCE_PAGE_URL,
                "manifest_url": MANIFEST_URL,
                "detail_bee_url": DETAIL_BEE_URL,
                "article_count": len(archived_articles),
                "articles": [
                    {
                        "title": article.title,
                        "commerce_id": article.commerce_id,
                        "source_url": article.source_url,
                        "article_json_path": article.article_json_path,
                        "detail_shell_path": article.detail_shell_path,
                        "rendered_html_path": article.rendered_html_path,
                        "image_paths": article.image_paths,
                    }
                    for article in archived_articles
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive the Douyin rule explain page and assets.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/source_archives/douyin_rule_explain/full_archive_2026-03-11"),
        help="Directory to store the local archive.",
    )
    args = parser.parse_args()
    archive_rules(args.output_dir.resolve())
    print(args.output_dir.resolve())


if __name__ == "__main__":
    main()
