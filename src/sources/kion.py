import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.utils import parse_datetime, valid_row

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:\s*/\s*\d{2}:\d{2}:\d{2})?\b")


def _normalize_detail_links(page_url: str, html: str, limit: int) -> list[str]:
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


def _extract_meta(soup: BeautifulSoup, key: str, attr: str = "name") -> str:
    node = soup.find("meta", attrs={attr: key})
    if not node:
        return ""
    return (node.get("content") or "").strip()


def _parse_detail(detail_url: str, source_id: str, source_url: str) -> dict:
    response = requests.get(detail_url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title = _extract_meta(soup, "og:title", attr="property")
    if not title:
        h = soup.select_one("main h1, main h2, h1, h2")
        title = h.get_text(" ", strip=True) if h else ""
    title = re.sub(r"\s+\|\s+KION GROUP AG$", "", title).strip()

    desc = _extract_meta(soup, "description")
    if not desc:
        desc = _extract_meta(soup, "og:description", attr="property")
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


def collect_kion_rows(source: dict) -> list[dict]:
    source_id = str(source["id"])
    source_url = str(source["url"])
    max_items = int(source.get("max_items", 80))

    listing = requests.get(source_url, timeout=20)
    listing.raise_for_status()
    detail_links = _normalize_detail_links(source_url, listing.text, max_items)

    rows: list[dict] = []
    for detail_link in detail_links:
        try:
            row = _parse_detail(detail_link, source_id, source_url)
            if valid_row(row):
                rows.append(row)
        except Exception as exc:
            print(f"[WARN] Failed detail scrape ({source_id}): {detail_link} ({exc})")

    print(f"[INFO] Source={source_id}, mode=scrape_kion, valid_rows={len(rows)}")
    return rows
