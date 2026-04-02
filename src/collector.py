from src.config import load_runtime_config
from src.sources import collect_rows_for_source
from src.storage.supabase import create_supabase_client, upsert_rows
from src.utils import dedupe_rows


def run() -> int:
    config = load_runtime_config()

    client = create_supabase_client(config["supabase_url"], config["supabase_key"])
    table_name = config["table_name"]
    sources = config["sources"]

    rows: list[dict] = []
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

    low_quality = [r for r in rows if float(r.get("parse_quality_score", 0.0)) < 0.6]
    if low_quality:
        print(f"[WARN] Low quality rows detected (<0.6): {len(low_quality)}")

    written = upsert_rows(client, table_name, rows)
    print(f"[INFO] Upsert completed. Rows returned: {written}, rows sent: {len(rows)}")
    return 0
