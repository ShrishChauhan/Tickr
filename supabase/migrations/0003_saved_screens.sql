-- 0003_saved_screens.sql
-- Tickr P6.1: saved_screens — persist a screener universe + filter config per user.
-- Safe to re-run: every object is created with an idempotent guard.

create table if not exists public.saved_screens (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  name         text not null,
  universe_key text not null,
  filters      jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  unique (user_id, name)
);

alter table public.saved_screens enable row level security;

drop policy if exists "saved_screens_select_own" on public.saved_screens;
create policy "saved_screens_select_own"
  on public.saved_screens for select
  using (auth.uid() = user_id);

drop policy if exists "saved_screens_insert_own" on public.saved_screens;
create policy "saved_screens_insert_own"
  on public.saved_screens for insert
  with check (auth.uid() = user_id);

drop policy if exists "saved_screens_delete_own" on public.saved_screens;
create policy "saved_screens_delete_own"
  on public.saved_screens for delete
  using (auth.uid() = user_id);
