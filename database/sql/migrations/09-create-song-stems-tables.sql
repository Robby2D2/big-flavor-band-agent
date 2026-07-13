-- Migration 09: stem separation for the production tools (issue #67)
--
-- Demucs separates a song (or a specific cleaned version of it) into independently
-- editable/streamable stems (vocals, drums, bass, guitar, other). Separation runs
-- as a background job that a producer polls, so its lifecycle is tracked per
-- stem SET (queued -> running -> complete | failed), and the resulting stem files
-- are recorded per stem. Both catalog originals and existing versions are only ever
-- read; only new files under produced/{song_id}/stems/... are written.

CREATE TABLE IF NOT EXISTS song_stem_sets (
    id SERIAL PRIMARY KEY,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,

    -- The version whose audio was separated. NULL means the catalog original was
    -- separated; otherwise the specific song_versions row. ON DELETE SET NULL so
    -- deleting a version doesn't cascade away a stem set already derived from it.
    source_version_id INTEGER REFERENCES song_versions(id) ON DELETE SET NULL,

    -- Demucs model name used for separation (e.g. 'htdemucs_6s').
    model VARCHAR(64) NOT NULL,

    -- Background-job lifecycle so a producer polling can always tell a failed run
    -- from a successful one: 'queued' | 'running' | 'complete' | 'failed'.
    status VARCHAR(16) NOT NULL DEFAULT 'queued',

    -- Human-readable failure reason when status = 'failed'.
    error TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_song_stem_sets_song_id ON song_stem_sets (song_id);

CREATE TABLE IF NOT EXISTS song_stems (
    id SERIAL PRIMARY KEY,
    stem_set_id INTEGER NOT NULL REFERENCES song_stem_sets(id) ON DELETE CASCADE,

    -- Stem name as emitted by Demucs: vocals | drums | bass | guitar | piano | other.
    name VARCHAR(32) NOT NULL,

    -- Absolute container path to this stem's audio file under produced/.
    path TEXT NOT NULL,

    UNIQUE (stem_set_id, name)
);

CREATE INDEX IF NOT EXISTS idx_song_stems_stem_set_id ON song_stems (stem_set_id);

COMMENT ON TABLE song_stem_sets IS
    'One stem-separation run (background job) for a song or one of its versions; tracks status.';
COMMENT ON TABLE song_stems IS
    'Individual stems (vocals/drums/bass/guitar/other) produced by one stem set.';
