-- 0001_profiles.sql
-- Tickr P5.2: profiles table, RLS, auto-provisioning trigger, username RPCs.
-- Safe to re-run: every object is created with an idempotent guard.

-- ============================================================
-- 1. profiles table
-- ============================================================
create table if not exists public.profiles (
  id                uuid primary key references auth.users(id) on delete cascade,
  username          text not null unique,
  first_name        text,
  last_name         text,
  display_name      text,
  bio               text,
  avatar_url        text,
  profile_completed boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint profiles_username_format check (username ~ '^[a-z0-9_]{3,20}$')
);

-- ============================================================
-- 2. Row Level Security — own-row only, no public read
-- ============================================================
alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own"
  on public.profiles for insert
  with check (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- ============================================================
-- 3. updated_at maintenance
-- ============================================================
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- ============================================================
-- 4. handle_new_user() — auto-provision a profile row for EVERY
--    new auth.users row (email signup OR Google OAuth).
-- ============================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_meta            jsonb := new.raw_user_meta_data;
  v_is_oauth_signup boolean := (v_meta ->> 'username') is null;
  v_base_username   text;
  v_candidate       text;
  v_username        text;
  v_full_name       text;
  v_first_name      text;
  v_last_name       text;
  v_display_name    text;
  v_attempt         int := 0;
  v_max_attempts    int := 5;
begin
  if v_is_oauth_signup then
    -- ---- Derive a unique placeholder username for OAuth signups ----
    v_base_username := lower(regexp_replace(split_part(coalesce(new.email, 'user'), '@', 1), '[^a-z0-9_]', '', 'g'));
    if v_base_username is null or length(v_base_username) < 3 then
      v_base_username := 'user';
    end if;
    v_base_username := left(v_base_username, 15);

    v_candidate := v_base_username;
    loop
      exit when not exists (select 1 from public.profiles p where p.username = v_candidate);
      v_attempt := v_attempt + 1;
      exit when v_attempt >= v_max_attempts;
      v_candidate := left(v_base_username, 15) || floor(random() * 9000 + 1000)::int::text;
    end loop;

    if exists (select 1 from public.profiles p where p.username = v_candidate) then
      -- Bounded retries exhausted — collision-proof fallback, no extension dependency.
      v_candidate := left(
        left(v_base_username, 10) || '_' || substr(md5(random()::text || clock_timestamp()::text), 1, 8),
        20
      );
    end if;

    v_username := v_candidate;

    v_full_name    := coalesce(v_meta ->> 'full_name', v_meta ->> 'name');
    v_first_name   := coalesce(v_meta ->> 'given_name', split_part(v_full_name, ' ', 1));
    v_last_name    := coalesce(v_meta ->> 'family_name', nullif(trim(regexp_replace(v_full_name, '^\S+\s*', '')), ''));
    v_display_name := coalesce(v_full_name, nullif(trim(concat_ws(' ', v_first_name, v_last_name)), ''), v_username);
  else
    -- ---- Email/password signup: trust client-supplied metadata ----
    v_username     := lower(v_meta ->> 'username');
    v_first_name   := v_meta ->> 'first_name';
    v_last_name    := v_meta ->> 'last_name';
    v_display_name := coalesce(nullif(trim(concat_ws(' ', v_first_name, v_last_name)), ''), v_username);
  end if;

  insert into public.profiles (id, username, first_name, last_name, display_name, profile_completed)
  values (new.id, v_username, v_first_name, v_last_name, v_display_name, not v_is_oauth_signup)
  on conflict (id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ============================================================
-- 5. Narrow RPCs for username-based signup availability + login
--    (browser-callable by anon; expose nothing beyond exact-match lookups)
-- ============================================================
create or replace function public.username_exists(p_username text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from public.profiles where username = lower(p_username));
$$;

revoke all on function public.username_exists(text) from public;
grant execute on function public.username_exists(text) to anon, authenticated;

create or replace function public.get_email_for_username(p_username text)
returns text
language sql
security definer
set search_path = public, auth
stable
as $$
  select u.email
  from public.profiles p
  join auth.users u on u.id = p.id
  where p.username = lower(p_username)
  limit 1;
$$;

revoke all on function public.get_email_for_username(text) from public;
grant execute on function public.get_email_for_username(text) to anon, authenticated;
