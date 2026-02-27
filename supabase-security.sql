-- Run in Supabase SQL Editor to harden database security.
-- Idempotent: safe to run multiple times.

-- 1. Ensure RLS is enabled on all tables
ALTER TABLE public.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.signups ENABLE ROW LEVEL SECURITY;

-- 2. Drop overly permissive policies if they exist, recreate strict ones
DROP POLICY IF EXISTS "Users can manage own entries" ON public.entries;

CREATE POLICY "Users read own entries"
  ON public.entries FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users insert own entries"
  ON public.entries FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own entries"
  ON public.entries FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own entries"
  ON public.entries FOR DELETE
  USING (auth.uid() = user_id);

-- 3. Add constraints to prevent invalid data at the database level
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'entries_sleep_hours_check'
  ) THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_sleep_hours_check
      CHECK (sleep_hours >= 0 AND sleep_hours <= 24);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'entries_sleep_quality_check'
  ) THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_sleep_quality_check
      CHECK (sleep_quality >= 1 AND sleep_quality <= 5);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'entries_energy_check'
  ) THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_energy_check
      CHECK (energy >= 1 AND energy <= 5);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'entries_deep_work_check'
  ) THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_deep_work_check
      CHECK (deep_work_blocks >= 0 AND deep_work_blocks <= 20);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'entries_transcript_length'
  ) THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_transcript_length
      CHECK (length(transcript) <= 10000);
  END IF;
END $$;

-- 4. Revoke direct table access from anon role (force through RLS)
REVOKE ALL ON public.entries FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.entries TO authenticated;

-- 5. Add index for common query patterns (user_id + date)
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON public.entries(user_id, date DESC);

-- 6. Enable pgcrypto extension for potential future use
CREATE EXTENSION IF NOT EXISTS pgcrypto;
