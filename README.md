# Multi RSS -> Supabase

This project fetches multiple RSS feeds and stores `title / content / link` into Supabase.

## 1) Create Supabase table

Run [supabase_setup.sql](c:\Users\jo.hyeon.woo\Documents\AI_Code\afl_trend\supabase_setup.sql) in Supabase SQL Editor.

The table is `public.rss_items` and deduplication uses `(source_id, link)`.

## 2) Configure RSS sources

Edit [rss_sources.json](c:\Users\jo.hyeon.woo\Documents\AI_Code\afl_trend\rss_sources.json):

```json
[
  { "id": "toyota_shokki", "url": "https://www.toyota-shokki.co.jp/news/rss_news.xml" },
  { "id": "another_feed", "url": "https://example.com/rss.xml" }
]
```

## 3) Local run (venv)

```powershell
C:\Users\jo.hyeon.woo\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set env:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- Optional: `SUPABASE_TABLE` (default: `rss_items`)
- Optional: `RSS_SOURCES_FILE` (default: `rss_sources.json`)
- Optional: `RSS_SOURCES_JSON` (if set, it overrides file)

Run:

```powershell
.\.venv\Scripts\python.exe .\rss_to_supabase.py
```

## 4) GitHub Actions (07:30 KST daily)

Workflow: [.github/workflows/rss-to-supabase.yml](c:\Users\jo.hyeon.woo\Documents\AI_Code\afl_trend\.github\workflows\rss-to-supabase.yml)

- Cron: `30 22 * * *` (UTC) = `07:30 KST`
- GitHub Secrets:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
- Optional GitHub Variable:
  - `RSS_SOURCES_JSON` (JSON array for feed list)

If `RSS_SOURCES_JSON` is empty, workflow uses `rss_sources.json` in the repository.
