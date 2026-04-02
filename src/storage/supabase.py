from postgrest.exceptions import APIError
from supabase import Client, create_client


def create_supabase_client(supabase_url: str, supabase_key: str) -> Client:
    return create_client(supabase_url, supabase_key)


def upsert_rows(client: Client, table_name: str, rows: list[dict]) -> int:
    try:
        response = (
            client.table(table_name)
            .upsert(rows, on_conflict="source_id,link")
            .execute()
        )
    except APIError as exc:
        code = getattr(exc, "code", None) or (exc.args[0].get("code") if exc.args else None)
        if code == "PGRST205":
            raise RuntimeError(
                f"Table '{table_name}' not found. Create it in Supabase SQL Editor first."
            ) from exc
        raise
    return len(response.data or [])
