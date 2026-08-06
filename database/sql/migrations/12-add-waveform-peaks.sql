-- Migration 12: cache the waveform drawing envelope server-side.
--
-- The produce stem console draws a waveform per stem, but drawing only needs a
-- per-pixel min/max envelope. The browser used to get that by downloading and
-- decoding the whole audio file — and Demucs writes uncompressed WAV, so a
-- six-stem set was ~260 MB fetched and decoded on every tab open just to paint
-- a few thousand pixels.
--
-- The envelope is now computed once (src/production/waveform_peaks.py) and
-- cached here, so the browser fetches ~15 KB of JSON per row instead. It is
-- derived data: dropping these columns only costs a recompute.
--
-- Nothing here changes how audio is produced or stored. The stem/version files
-- on disk are untouched and remain what every DSP tool reads.

-- {"version": 1, "resolution": 2000, "scale": 127, "duration_seconds": 248.19,
--  "sample_rate": 44100, "channels": 2, "min": [...], "max": [...]}
-- min/max are ints in [-scale, scale]. "version" is checked on read, so bumping
-- PEAKS_FORMAT_VERSION invalidates every cached row without a backfill.
ALTER TABLE song_stems    ADD COLUMN IF NOT EXISTS waveform_peaks JSONB;
ALTER TABLE song_versions ADD COLUMN IF NOT EXISTS waveform_peaks JSONB;

COMMENT ON COLUMN song_stems.waveform_peaks IS
    'Cached drawing envelope {version,resolution,scale,duration_seconds,sample_rate,channels,min[],max[]}; NULL means not computed yet.';
COMMENT ON COLUMN song_versions.waveform_peaks IS
    'Cached drawing envelope for this version''s audio; cleared whenever audio_path is replaced.';
