-- Migration 07: song versions for the audio-cleanup audition/publish loop (issue #30)
--
-- auto_clean_recording produces a cleaned take; this table lets a producer keep
-- multiple audio versions of a song (the original is never overwritten) and mark
-- exactly one as the "published" version that the radio/stream serve. Every
-- version's audio is embedded separately in audio_embeddings (keyed by audio_path),
-- so audio-similarity search can surface any version.

CREATE TABLE IF NOT EXISTS song_versions (
    id SERIAL PRIMARY KEY,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,

    -- Absolute container path to this version's audio file (e.g.
    -- /app/audio_library/5_track.mp3 for the original, or a produced/ file for a
    -- cleaned take). One row per distinct audio file.
    audio_path TEXT NOT NULL,

    -- 'original' for the catalog source, 'cleaned' for an auto_clean_recording result.
    label VARCHAR(32) NOT NULL DEFAULT 'cleaned',

    -- Exactly one published version per song (enforced by the partial unique index below).
    is_published BOOLEAN NOT NULL DEFAULT FALSE,

    -- The before/after metrics diff and cleanup payload captured at approval time
    -- (steps_applied, aggressiveness, LUFS/peak/duration before+after, noise reduction).
    metrics JSONB,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (audio_path)
);

-- At most one published version per song.
CREATE UNIQUE INDEX IF NOT EXISTS idx_song_versions_one_published
    ON song_versions (song_id)
    WHERE is_published;

CREATE INDEX IF NOT EXISTS idx_song_versions_song_id ON song_versions (song_id);

COMMENT ON TABLE song_versions IS
    'Audio versions of a song (original + cleaned takes); exactly one is published and served.';
