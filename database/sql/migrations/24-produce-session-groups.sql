-- Migration 24: a session's song groups become catalog songs
--
-- Review of a session is now only about *grouping* takes into songs. A producer
-- then produces a group: it becomes one new catalog song, every take in it that
-- was not discarded becomes one of that song's versions, and which version is
-- the default is chosen on the produce page like any other song's (SESS-15,
-- SESS-19). The per-group "keeper" that used to stand in for that choice goes.
--
-- Session songs take their ids from a range of their own. `songs.id` has no
-- sequence because catalog ids come from bigflavorband.com (max ~2.6k), and a
-- later scrape must never collide with a song made here. The range is also how
-- search and radio recognise a session song that has no default yet and keep
-- it out of sight (SESS-20): `database.SESSION_SONG_ID_START` must match.

CREATE SEQUENCE IF NOT EXISTS session_song_id_seq START WITH 1000000 MINVALUE 1000000;

-- The catalog song a group was produced into. SET NULL on delete so removing
-- the song only un-produces the group; its takes are untouched.
ALTER TABLE session_take_groups
    ADD COLUMN IF NOT EXISTS song_id INTEGER REFERENCES songs(id) ON DELETE SET NULL;

-- The version a take became. This is what makes producing a group again add
-- only the takes that joined it since, never a second copy of one already in.
ALTER TABLE session_takes
    ADD COLUMN IF NOT EXISTS song_version_id INTEGER
        REFERENCES song_versions(id) ON DELETE SET NULL;

ALTER TABLE session_take_groups DROP COLUMN IF EXISTS keeper_take_id;

COMMENT ON COLUMN session_take_groups.song_id IS
    'The catalog song this group was produced into; NULL until a producer produces it.';
COMMENT ON COLUMN session_takes.song_version_id IS
    'The song version this take became when its group was produced; NULL while staged.';
