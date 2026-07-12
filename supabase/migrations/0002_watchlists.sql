-- 0002_watchlists.sql
-- Tickr P5.3: watchlist_items, tags, watchlist_item_tags (many-to-many junction).
-- Safe to re-run: every object is created with an idempotent guard.

create extension if not exists "pgcrypto";

-- ============================================================
-- 1. watchlist_items — one row per tracked asset per user
-- ============================================================
create table if not exists public.watchlist_items (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  ticker       text not null,
  asset_type   text not null,
  display_name text,
  notes        text,
  added_at     timestamptz not null default now(),
  unique (user_id, ticker)
);

alter table public.watchlist_items enable row level security;

drop policy if exists "watchlist_items_select_own" on public.watchlist_items;
create policy "watchlist_items_select_own"
  on public.watchlist_items for select
  using (auth.uid() = user_id);

drop policy if exists "watchlist_items_insert_own" on public.watchlist_items;
create policy "watchlist_items_insert_own"
  on public.watchlist_items for insert
  with check (auth.uid() = user_id);

drop policy if exists "watchlist_items_update_own" on public.watchlist_items;
create policy "watchlist_items_update_own"
  on public.watchlist_items for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "watchlist_items_delete_own" on public.watchlist_items;
create policy "watchlist_items_delete_own"
  on public.watchlist_items for delete
  using (auth.uid() = user_id);

-- ============================================================
-- 2. tags — per-user tag vocabulary (auto-derived + custom)
-- ============================================================
create table if not exists public.tags (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  name            text not null,
  is_auto_derived boolean not null default false
);

create unique index if not exists tags_user_id_lower_name_key
  on public.tags (user_id, lower(name));

alter table public.tags enable row level security;

drop policy if exists "tags_select_own" on public.tags;
create policy "tags_select_own"
  on public.tags for select
  using (auth.uid() = user_id);

drop policy if exists "tags_insert_own" on public.tags;
create policy "tags_insert_own"
  on public.tags for insert
  with check (auth.uid() = user_id);

drop policy if exists "tags_update_own" on public.tags;
create policy "tags_update_own"
  on public.tags for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "tags_delete_own" on public.tags;
create policy "tags_delete_own"
  on public.tags for delete
  using (auth.uid() = user_id);

-- ============================================================
-- 3. watchlist_item_tags — many-to-many junction, no user_id
--    column of its own; ownership is implied through the two
--    parent tables, so policies use EXISTS subqueries.
-- ============================================================
create table if not exists public.watchlist_item_tags (
  item_id uuid not null references public.watchlist_items(id) on delete cascade,
  tag_id  uuid not null references public.tags(id) on delete cascade,
  primary key (item_id, tag_id)
);

alter table public.watchlist_item_tags enable row level security;

drop policy if exists "watchlist_item_tags_select_own" on public.watchlist_item_tags;
create policy "watchlist_item_tags_select_own"
  on public.watchlist_item_tags for select
  using (
    exists (
      select 1 from public.watchlist_items wi
      where wi.id = item_id and wi.user_id = auth.uid()
    )
  );

drop policy if exists "watchlist_item_tags_insert_own" on public.watchlist_item_tags;
create policy "watchlist_item_tags_insert_own"
  on public.watchlist_item_tags for insert
  with check (
    exists (
      select 1 from public.watchlist_items wi
      where wi.id = item_id and wi.user_id = auth.uid()
    )
    and exists (
      select 1 from public.tags t
      where t.id = tag_id and t.user_id = auth.uid()
    )
  );

drop policy if exists "watchlist_item_tags_delete_own" on public.watchlist_item_tags;
create policy "watchlist_item_tags_delete_own"
  on public.watchlist_item_tags for delete
  using (
    exists (
      select 1 from public.watchlist_items wi
      where wi.id = item_id and wi.user_id = auth.uid()
    )
  );
