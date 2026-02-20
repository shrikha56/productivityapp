-- Run this in Supabase Dashboard → SQL Editor (new query)
-- Creates the table for beta signups.

create table if not exists public.signups (
  id uuid default gen_random_uuid() primary key,
  email text unique not null,
  created_at timestamptz default now()
);

alter table public.signups enable row level security;

-- Allow inserts with anon key (e.g. from your backend using SUPABASE_ANON_KEY).
create policy "Allow anon insert"
  on public.signups for insert to anon
  with check (true);
