from datetime import datetime, timezone
from typing import Any

import feedparser

from src.utils import calc_quality_score, clean_text, parse_datetime, valid_row


def _pick_content(entry: Any) -> str:
    content = getattr(entry, "content", None)
    if content and isinstance(content, list) and len(content) > 0:
        first = content[0]
        if isinstance(first, dict):
            return (first.get("value") or "").strip()
    return (getattr(entry, "summary", "") or "").strip()


def _to_row(entry: Any, source_id: str, source_url: str) -> dict[str, Any]:
    title = (getattr(entry, "title", "") or "").strip()
    link = (getattr(entry, "link", "") or "").strip()
    content = _pick_content(entry)
    content_clean = clean_text(content)
    published_at = parse_datetime(
        getattr(entry, "published", None)
        or getattr(entry, "updated", None)
        or getattr(entry, "pubDate", None)
    )
    quality = calc_quality_score(title, content_clean, published_at)
    return {
        "title": title,
        "content": content,
        "content_clean": content_clean,
        "content_raw": content,
        "raw_html": None,
        "link": link,
        "published_at": published_at,
        "source_id": source_id,
        "source_url": source_url,
        "parse_method": "rss_feedparser",
        "parse_quality_score": quality,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_rss_rows(source: dict) -> list[dict]:
    source_id = str(source["id"])
    source_url = str(source["url"])

    feed = feedparser.parse(source_url)
    if getattr(feed, "bozo", 0):
        print(
            f"[WARN] RSS parse warning ({source_id}): "
            f"{getattr(feed, 'bozo_exception', 'unknown')}"
        )

    entries = getattr(feed, "entries", [])
    rows = [_to_row(entry, source_id, source_url) for entry in entries]
    rows = [row for row in rows if valid_row(row)]
    print(f"[INFO] Source={source_id}, mode=rss, entries={len(entries)}, valid_rows={len(rows)}")
    return rows
