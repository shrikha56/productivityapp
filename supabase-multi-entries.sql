-- Run in Supabase SQL Editor to allow multiple entries per day.
-- Adds entry_number and is_follow_up columns; drops the unique(user_id, date) constraint.

-- 1. Drop the unique constraint so users can have multiple entries per day
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_user_id_date_key;

-- 2. Add new columns
ALTER TABLE public.entries
  ADD COLUMN IF NOT EXISTS entry_number smallint DEFAULT 1,
  ADD COLUMN IF NOT EXISTS is_follow_up boolean DEFAULT false;

-- 3. Add a new unique constraint: one entry_number per user per date
ALTER TABLE public.entries
  ADD CONSTRAINT entries_user_date_number_key UNIQUE (user_id, date, entry_number);

-- 4. Update deep_work_blocks constraint to max 5
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_deep_work_check;
ALTER TABLE public.entries ADD CONSTRAINT entries_deep_work_check
  CHECK (deep_work_blocks >= 0 AND deep_work_blocks <= 5);
