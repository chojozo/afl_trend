create table if not exists public.rss_items (
  id bigint generated always as identity primary key,
  title text not null,
  content text,
  link text not null,
  source_id text not null,
  source_url text not null,
  published_at timestamptz,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create unique index if not exists rss_items_source_link_key
  on public.rss_items (source_id, link);

create index if not exists rss_items_published_at_idx
  on public.rss_items (published_at desc);
