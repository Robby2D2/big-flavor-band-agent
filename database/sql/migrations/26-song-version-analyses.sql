-- Migration 26: what Start analysis found, kept per version
--
-- A pass used to live in the browser, so its findings were gone the moment the
-- producer left the page, and the only way back to them was minutes of measuring
-- again (PROD-22). The server runs the pass now and keeps its last outcome here:
-- one row per version, replaced by the next pass.
--
-- stem_set_id says which stems the findings describe. They stop counting once a
-- newer set exists for the version. It is NULL when a pass failed or was
-- cancelled before it had any stems.

CREATE TABLE IF NOT EXISTS song_version_analyses (
    source_version_id INTEGER PRIMARY KEY REFERENCES song_versions(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    stem_set_id INTEGER REFERENCES song_stem_sets(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL,
    rows JSONB NOT NULL DEFAULT '[]',
    outcomes JSONB NOT NULL DEFAULT '[]',
    error TEXT,
    finished_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE song_version_analyses IS
    'The last Start analysis outcome for each version; survives leaving the page.';
