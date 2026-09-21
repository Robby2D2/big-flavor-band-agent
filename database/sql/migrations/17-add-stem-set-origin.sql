-- Where a stem set's audio came from.
--
-- Until now every set was made by running Demucs (`origin` NULL, read as
-- 'separated'). Saving a version from the fix queue now keeps the per-stem audio
-- it just rendered as that version's stem set, so a producer who saves fixes and
-- then selects the new version does not have to wait minutes for a separation of
-- a mix that was itself assembled from stems — which would also pile a second
-- generation of separation artifacts on top of the first.
--
--   NULL / 'separated'  — Demucs output.
--   'fixes'             — the stems the fix queue rendered. They sum to this
--                         version's audio.
--   'fixes_premaster'   — same, but whole-mix fixes ran *after* the remix, so
--                         they sum to the mix before mastering, not to the saved
--                         file. Worth telling the producer rather than letting
--                         them wonder why the parts do not quite add up.
--
-- Nullable with no backfill: an absent value already means 'separated', and
-- every existing row is one.
ALTER TABLE song_stem_sets ADD COLUMN IF NOT EXISTS origin TEXT;

COMMENT ON COLUMN song_stem_sets.origin IS
  'NULL/separated = Demucs; fixes = rendered by the fix queue; '
  'fixes_premaster = rendered by the fix queue, before master-scoped fixes.';
