from src.sources.kion import collect_kion_rows
from src.sources.rss import collect_rss_rows


def collect_rows_for_source(source: dict) -> list[dict]:
    source_type = str(source.get("type", "rss"))
    if source_type == "scrape_kion":
        return collect_kion_rows(source)
    if source_type == "rss":
        return collect_rss_rows(source)
    raise RuntimeError(f"Unsupported source type: {source_type} (source id={source.get('id')})")
