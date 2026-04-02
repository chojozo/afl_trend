alter table public.rss_items
  add column if not exists content_clean text,
  add column if not exists content_raw text,
  add column if not exists raw_html text,
  add column if not exists parse_method text,
  add column if not exists parse_quality_score numeric(4,2);
