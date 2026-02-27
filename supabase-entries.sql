-- Run in Supabase SQL Editor (after signups table exists)
-- Creates the entries table for daily check-ins.

create table if not exists public.entries (
  id uuid default gen_random_uuid() primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  sleep_hours numeric(3,1),
  sleep_quality smallint,
  energy smallint,
  deep_work_blocks smallint,
  transcript text,
  reflection_summary text,
  likely_drivers jsonb default '[]',
  predicted_impact text,
  experiment_for_tomorrow text,
  is_outlier boolean default false,
  created_at timestamptz default now(),
  unique(user_id, date)
);

alter table public.entries enable row level security;

create policy "Users can manage own entries"
  on public.entries for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
