import os
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import feedparser
from dateutil import parser as date_parser
from postgrest.exceptions import APIError
from supabase import Client, create_client

TABLE_NAME = os.getenv("SUPABASE_TABLE", "rss_items")
SOURCES_FILE = os.getenv("RSS_SOURCES_FILE", "rss_sources.json")
DEFAULT_SOURCES = [
    {
        "id": "toyota_shokki",
        "url": "https://www.toyota-shokki.co.jp/news/rss_news.xml",
    }
]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_datetime(value: str | None) -> str | None:
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def pick_content(entry: Any) -> str:
    content = getattr(entry, "content", None)
    if content and isinstance(content, list) and len(content) > 0:
        first = content[0]
        if isinstance(first, dict):
            return (first.get("value") or "").strip()
    return (getattr(entry, "summary", "") or "").strip()


def parse_sources_from_json(raw: str) -> list[dict[str, str]]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("RSS_SOURCES_JSON must be a JSON array.")

    sources: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id", "")).strip()
        url = str(item.get("url", "")).strip()
        if source_id and url:
            sources.append({"id": source_id, "url": url})
    return sources


def load_sources() -> list[dict[str, str]]:
    raw = os.getenv("RSS_SOURCES_JSON")
    if raw:
        sources = parse_sources_from_json(raw)
        if sources:
            return sources
        raise RuntimeError("RSS_SOURCES_JSON exists but contains no valid sources.")

    file_path = Path(SOURCES_FILE)
    if file_path.exists():
        text = file_path.read_text(encoding="utf-8")
        sources = parse_sources_from_json(text)
        if sources:
            return sources
        raise RuntimeError(f"{SOURCES_FILE} exists but contains no valid sources.")

    return DEFAULT_SOURCES


def to_row(entry: Any, source_id: str, source_url: str) -> dict[str, Any]:
    title = (getattr(entry, "title", "") or "").strip()
    link = (getattr(entry, "link", "") or "").strip()
    content = pick_content(entry)
    published_at = parse_datetime(
        getattr(entry, "published", None)
        or getattr(entry, "updated", None)
        or getattr(entry, "pubDate", None)
    )

    return {
        "title": title,
        "content": content,
        "link": link,
        "published_at": published_at,
        "source_id": source_id,
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def valid_row(row: dict[str, Any]) -> bool:
    return bool(row["title"] and row["link"])


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["source_id"]), str(row["link"]))
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = row
            continue

        existing_pub = existing.get("published_at") or ""
        candidate_pub = row.get("published_at") or ""
        if candidate_pub >= existing_pub:
            deduped[key] = row

    return list(deduped.values())


def run() -> int:
    supabase_url = require_env("SUPABASE_URL")
    supabase_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    client: Client = create_client(supabase_url, supabase_key)

    sources = load_sources()
    rows: list[dict[str, Any]] = []
    for source in sources:
        source_id = source["id"]
        source_url = source["url"]
        feed = feedparser.parse(source_url)
        if getattr(feed, "bozo", 0):
            print(
                f"[WARN] RSS parse warning ({source_id}): "
                f"{getattr(feed, 'bozo_exception', 'unknown')}"
            )

        entries = getattr(feed, "entries", [])
        source_rows = [to_row(entry, source_id, source_url) for entry in entries]
        source_rows = [row for row in source_rows if valid_row(row)]
        rows.extend(source_rows)
        print(f"[INFO] Source={source_id}, entries={len(entries)}, valid_rows={len(source_rows)}")

    if not rows:
        print("[INFO] No valid RSS entries found.")
        return 0

    before = len(rows)
    rows = dedupe_rows(rows)
    removed = before - len(rows)
    if removed > 0:
        print(f"[INFO] Deduped in-batch duplicates: {removed}")

    try:
        response = (
            client.table(TABLE_NAME)
            .upsert(rows, on_conflict="source_id,link")
            .execute()
        )
    except APIError as exc:
        code = getattr(exc, "code", None) or (exc.args[0].get("code") if exc.args else None)
        if code == "PGRST205":
            raise RuntimeError(
                f"Table '{TABLE_NAME}' not found. Create it in Supabase SQL Editor first."
            ) from exc
        raise

    written = len(response.data or [])
    print(f"[INFO] Upsert completed. Rows returned: {written}, rows sent: {len(rows)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise
