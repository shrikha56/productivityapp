-- =============================================================================
-- Supabase RLS + Encryption Hardening
-- Run in Supabase Dashboard → SQL Editor
-- Idempotent: safe to run multiple times.
-- =============================================================================
--
-- SECURITY MODEL:
-- 1. RLS ensures users can only access their own rows (when using anon/authenticated key).
-- 2. transcript and reflection_summary are encrypted in application code before insert.
--    The DB stores ciphertext; decryption happens in the API layer.
-- 3. Backend uses service_role key (bypasses RLS) but enforces user_id via JWT.
-- 4. This script strengthens RLS and adds optional encryption format checks.
-- =============================================================================

-- 1. Enable RLS on all sensitive tables
ALTER TABLE public.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.signups ENABLE ROW LEVEL SECURITY;

-- 2. Drop old/redundant policies, create strict per-operation policies
DROP POLICY IF EXISTS "Users can manage own entries" ON public.entries;
DROP POLICY IF EXISTS "Users read own entries" ON public.entries;
DROP POLICY IF EXISTS "Users insert own entries" ON public.entries;
DROP POLICY IF EXISTS "Users update own entries" ON public.entries;
DROP POLICY IF EXISTS "Users delete own entries" ON public.entries;

CREATE POLICY "Users read own entries"
  ON public.entries FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users insert own entries"
  ON public.entries FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own entries"
  ON public.entries FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own entries"
  ON public.entries FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- 3. Restrict entries: anon cannot access; authenticated gets RLS-scoped access; service_role full
REVOKE ALL ON public.entries FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.entries TO authenticated;
GRANT ALL ON public.entries TO service_role;

-- 4. Signups: anon can insert (for join/beta), no read for anon
DROP POLICY IF EXISTS "Allow anon insert" ON public.signups;
CREATE POLICY "Allow anon insert for signups"
  ON public.signups FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Service role full access signups"
  ON public.signups FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- 5. Data validation constraints
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entries_sleep_hours_check') THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_sleep_hours_check
      CHECK (sleep_hours >= 0 AND sleep_hours <= 24);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entries_sleep_quality_check') THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_sleep_quality_check
      CHECK (sleep_quality >= 1 AND sleep_quality <= 5);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entries_energy_check') THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_energy_check
      CHECK (energy >= 1 AND energy <= 5);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entries_deep_work_check') THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_deep_work_check
      CHECK (deep_work_blocks >= 0 AND deep_work_blocks <= 5);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entries_transcript_length') THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_transcript_length
      CHECK (length(transcript) <= 10000);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entries_reflection_length') THEN
    ALTER TABLE public.entries ADD CONSTRAINT entries_reflection_length
      CHECK (length(reflection_summary) <= 15000);
  END IF;
END $$;

-- 6. Optional: Reject obviously unencrypted sensitive data (Fernet output is base64)
--    Only run if ALL existing rows have encrypted values. Uncomment to enable:
/*
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_transcript_encrypted_format;
ALTER TABLE public.entries ADD CONSTRAINT entries_transcript_encrypted_format
  CHECK (
    transcript IS NULL
    OR transcript = ''
    OR (length(transcript) >= 44 AND transcript ~ '^[A-Za-z0-9+/=-]+$')
  );

ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_reflection_encrypted_format;
ALTER TABLE public.entries ADD CONSTRAINT entries_reflection_encrypted_format
  CHECK (
    reflection_summary IS NULL
    OR reflection_summary = ''
    OR (length(reflection_summary) >= 44 AND reflection_summary ~ '^[A-Za-z0-9+/=-]+$')
  );
*/

-- 7. Index for common queries
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON public.entries(user_id, date DESC);

-- 8. Enable pgcrypto (for future server-side crypto if needed)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
