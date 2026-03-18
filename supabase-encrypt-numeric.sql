-- =============================================================================
-- Migrate numeric columns to text for application-level encryption.
-- Run in Supabase Dashboard → SQL Editor BEFORE deploying the new server code.
-- Idempotent: safe to run multiple times.
-- =============================================================================
--
-- WHY: sleep_hours, sleep_quality, energy, deep_work_blocks are currently
-- stored as numeric/int2. To encrypt them with Fernet (application-layer),
-- the columns must be text so they can hold ciphertext.
-- Validation still happens in application code (clamp_int / clamp_float).
-- =============================================================================

-- 1. Drop numeric CHECK constraints (can't enforce range on ciphertext)
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_sleep_hours_check;
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_sleep_quality_check;
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_energy_check;
ALTER TABLE public.entries DROP CONSTRAINT IF EXISTS entries_deep_work_check;

-- 2. Change column types from numeric/int to text
ALTER TABLE public.entries ALTER COLUMN sleep_hours TYPE text USING sleep_hours::text;
ALTER TABLE public.entries ALTER COLUMN sleep_quality TYPE text USING sleep_quality::text;
ALTER TABLE public.entries ALTER COLUMN energy TYPE text USING energy::text;
ALTER TABLE public.entries ALTER COLUMN deep_work_blocks TYPE text USING deep_work_blocks::text;
