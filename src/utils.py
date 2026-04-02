from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as date_parser


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


def valid_row(row: dict[str, Any]) -> bool:
    return bool(row.get("title") and row.get("link"))


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


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())


def calc_quality_score(title: str, content_clean: str, published_at: str | None) -> float:
    score = 0.0
    if title and len(title) >= 8:
        score += 0.35
    if content_clean and len(content_clean) >= 120:
        score += 0.45
    if published_at:
        score += 0.20
    return round(min(score, 1.0), 2)
