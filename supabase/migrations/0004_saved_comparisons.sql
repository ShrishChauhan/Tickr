-- 0004_saved_comparisons.sql
-- Tickr P6.2: saved_comparisons — persist a /compare ticker set per user.
-- Safe to re-run: every object is created with an idempotent guard.

create table if not exists public.saved_comparisons (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  name       text not null,
  tickers    jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, name)
);

alter table public.saved_comparisons enable row level security;

drop policy if exists "saved_comparisons_select_own" on public.saved_comparisons;
create policy "saved_comparisons_select_own"
  on public.saved_comparisons for select
  using (auth.uid() = user_id);

drop policy if exists "saved_comparisons_insert_own" on public.saved_comparisons;
create policy "saved_comparisons_insert_own"
  on public.saved_comparisons for insert
  with check (auth.uid() = user_id);

drop policy if exists "saved_comparisons_delete_own" on public.saved_comparisons;
create policy "saved_comparisons_delete_own"
  on public.saved_comparisons for delete
  using (auth.uid() = user_id);
