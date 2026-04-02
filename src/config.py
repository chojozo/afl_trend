import json
import os
from pathlib import Path
from typing import Any

DEFAULT_TABLE_NAME = "rss_items"
DEFAULT_SOURCES_FILE = "rss_sources.json"
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


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
    sources_file = os.getenv("RSS_SOURCES_FILE", DEFAULT_SOURCES_FILE)
    raw = os.getenv("RSS_SOURCES_JSON")
    if raw:
        sources = parse_sources_from_json(raw)
        if sources:
            return sources
        raise RuntimeError("RSS_SOURCES_JSON exists but contains no valid sources.")

    file_path = Path(sources_file)
    if file_path.exists():
        text = file_path.read_text(encoding="utf-8")
        sources = parse_sources_from_json(text)
        if sources:
            return sources
        raise RuntimeError(f"{sources_file} exists but contains no valid sources.")

    return DEFAULT_SOURCES


def load_runtime_config() -> dict[str, Any]:
    return {
        "supabase_url": require_env("SUPABASE_URL"),
        "supabase_key": require_env("SUPABASE_SERVICE_ROLE_KEY"),
        "table_name": os.getenv("SUPABASE_TABLE", DEFAULT_TABLE_NAME),
        "sources": load_sources(),
    }
