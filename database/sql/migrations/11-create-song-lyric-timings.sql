-- Migration 11: timed lyrics so the UI can follow along while a song plays.
--
-- Whisper already returns a start/end timestamp per transcribed segment; until now
-- lyrics_jobs threw them away and stored only the joined text. This table keeps
-- those timings as a derived sidecar to the lyric text.
--
-- The lyric TEXT itself stays exactly where it was — text_embeddings
-- (content_type = 'lyrics') remains the single source of truth for lyric search.
-- Timings live here instead of in that table because text_embeddings is keyed
-- UNIQUE(song_id, content_type) around an embedding column, and lyric search
-- filters on content_type; a second row there would risk polluting search results.
--
-- The payload is one JSONB document per song rather than a row per line: it is
-- always fetched whole for playback and never queried by field, so a document
-- keeps reads to a single row (~3-8 KB) and avoids a 100k-row line table.

CREATE TABLE IF NOT EXISTS song_lyric_timings (
    id SERIAL PRIMARY KEY,

    -- One timing record per song; a re-extraction replaces it in place.
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,

    -- Shape version of the `lines` document, so the payload can evolve without
    -- a migration. 1 = [{start, end, text, confidence, words?}].
    format_version INTEGER NOT NULL DEFAULT 1,

    -- How the timings were produced: 'whisper' (transcription timestamps),
    -- 'aligned' (forced alignment against edited text), 'manual' (hand-authored).
    source VARCHAR(16) NOT NULL DEFAULT 'whisper',

    -- Transcription model that produced them (e.g. 'large-v3').
    model VARCHAR(64),

    -- Which audio the timings were measured against: 'mix' | 'vocals_stem'.
    -- Vocal-isolated transcription lines up noticeably better on sung vocals, so
    -- this records whether a given song got the better path.
    audio_source VARCHAR(32) NOT NULL DEFAULT 'mix',

    -- 'current' while the timings match the stored lyric text; 'stale' once the
    -- text is hand-edited, so the player can fall back to plain lyrics instead
    -- of highlighting the wrong words.
    status VARCHAR(16) NOT NULL DEFAULT 'current',

    -- [{start, end, text, confidence, words: [{s, e, t, p}]}] — see format_version.
    lines JSONB NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (song_id)
);

CREATE INDEX IF NOT EXISTS idx_song_lyric_timings_song_id
    ON song_lyric_timings (song_id);
