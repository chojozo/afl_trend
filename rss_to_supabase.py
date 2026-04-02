import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from postgrest.exceptions import APIError
from supabase import Client, create_client

TABLE_NAME = os.getenv("SUPABASE_TABLE", "rss_items")
SOURCES_FILE = os.getenv("RSS_SOURCES_FILE", "rss_sources.json")
DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "id": "toyota_shokki",
        "type": "rss",
        "url": "https://www.toyota-shokki.co.jp/news/rss_news.xml",
    },
    {
        "id": "kion_press_releases",
        "type": "scrape_kion",
        "url": "https://www.kiongroup.com/en/News-Stories/Press-Releases/",
        "max_items": 80,
    },
    {
        "id": "kion_financial_news",
        "type": "scrape_kion",
        "url": "https://www.kiongroup.com/en/Investor-Relations/Financial-News/Press-Releases-Detail.html",
        "max_items": 80,
    },
]

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:\s*/\s*\d{2}:\d{2}:\d{2})?\b")


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


def parse_sources_from_json(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("RSS_SOURCES_JSON must be a JSON array.")

    sources: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id", "")).strip()
        url = str(item.get("url", "")).strip()
        if not source_id or not url:
            continue
        source_type = str(item.get("type", "rss")).strip() or "rss"
        max_items = item.get("max_items", 80)
        try:
            max_items = int(max_items)
        except Exception:
            max_items = 80

        sources.append(
            {
                "id": source_id,
                "type": source_type,
                "url": url,
                "max_items": max(1, max_items),
            }
        )
    return sources


def load_sources() -> list[dict[str, Any]]:
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


def to_rss_row(entry: Any, source_id: str, source_url: str) -> dict[str, Any]:
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


def normalize_kion_detail_links(page_url: str, html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[str] = []
    for anchor in soup.select("a[href*='Press-Releases-Detail.html']"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        full_url = urljoin(page_url, href)
        parsed = urlparse(full_url)
        qs = parse_qs(parsed.query)
        ids = qs.get("id")
        if not ids or not ids[0].strip():
            continue
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?id={ids[0].strip()}"
        if clean_url in seen:
            continue
        seen.add(clean_url)
        links.append(clean_url)
        if len(links) >= limit:
            break
    return links


def extract_meta(soup: BeautifulSoup, key: str, attr: str = "name") -> str:
    node = soup.find("meta", attrs={attr: key})
    if not node:
        return ""
    return (node.get("content") or "").strip()


def parse_kion_detail(detail_url: str, source_id: str, source_url: str) -> dict[str, Any]:
    response = requests.get(detail_url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title = extract_meta(soup, "og:title", attr="property")
    if not title:
        h = soup.select_one("main h1, main h2, h1, h2")
        title = h.get_text(" ", strip=True) if h else ""
    title = re.sub(r"\s+\|\s+KION GROUP AG$", "", title).strip()

    desc = extract_meta(soup, "description")
    if not desc:
        desc = extract_meta(soup, "og:description", attr="property")

    if not desc:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.select("main p")]
        paragraphs = [p for p in paragraphs if p]
        desc = "\n".join(paragraphs[:3]).strip()

    text_blob = soup.get_text(" ", strip=True)
    date_match = DATE_RE.search(text_blob)
    published_at = parse_datetime(date_match.group(0)) if date_match else None

    return {
        "title": title,
        "content": desc,
        "link": detail_url,
        "published_at": published_at,
        "source_id": source_id,
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def scrape_kion_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = str(source["id"])
    source_url = str(source["url"])
    max_items = int(source.get("max_items", 80))

    listing = requests.get(source_url, timeout=20)
    listing.raise_for_status()
    detail_links = normalize_kion_detail_links(source_url, listing.text, max_items)

    rows: list[dict[str, Any]] = []
    for detail_link in detail_links:
        try:
            rows.append(parse_kion_detail(detail_link, source_id, source_url))
        except Exception as exc:
            print(f"[WARN] Failed detail scrape ({source_id}): {detail_link} ({exc})")

    return rows


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


def collect_rows_for_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = str(source["id"])
    source_url = str(source["url"])
    source_type = str(source.get("type", "rss"))

    if source_type == "scrape_kion":
        rows = scrape_kion_rows(source)
        rows = [row for row in rows if valid_row(row)]
        print(f"[INFO] Source={source_id}, mode=scrape_kion, valid_rows={len(rows)}")
        return rows

    feed = feedparser.parse(source_url)
    if getattr(feed, "bozo", 0):
        print(
            f"[WARN] RSS parse warning ({source_id}): "
            f"{getattr(feed, 'bozo_exception', 'unknown')}"
        )
    entries = getattr(feed, "entries", [])
    rows = [to_rss_row(entry, source_id, source_url) for entry in entries]
    rows = [row for row in rows if valid_row(row)]
    print(f"[INFO] Source={source_id}, mode=rss, entries={len(entries)}, valid_rows={len(rows)}")
    return rows


def run() -> int:
    supabase_url = require_env("SUPABASE_URL")
    supabase_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    client: Client = create_client(supabase_url, supabase_key)

    sources = load_sources()
    rows: list[dict[str, Any]] = []
    for source in sources:
        rows.extend(collect_rows_for_source(source))

    if not rows:
        print("[INFO] No valid entries found.")
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
