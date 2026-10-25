-- Migration 25: a split take's words are read again, in the background
--
-- A producer can split a take in two where the band ran one song straight into
-- the next (SESS-22). The scan keeps only a take's words, not when each was
-- sung, so neither half can be given its share of the old transcript — Whisper
-- reads each half again. That runs for minutes, after the split has returned.
--
-- Until it lands, a half has no transcript, which would otherwise read as an
-- instrumental: an honest-looking label that is false (SESS-12). This flag is
-- what tells the page the words are still coming. Durable rather than in-memory
-- so a backend restart mid-read resumes it instead of leaving the half wordless.

ALTER TABLE session_takes
    ADD COLUMN IF NOT EXISTS transcript_pending BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN session_takes.transcript_pending IS
    'The take''s words are being read again after a split; transcript is not final.';
