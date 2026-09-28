-- Migration 21: group a session's takes by the song they are attempts at
--
-- A scan produces a flat list of takes, so the several attempts the band made at
-- one song read as unrelated stretches. Which takes belong together is a guess
-- drawn from what was sung (never a catalog lookup), and a guess is wrong often
-- enough that the *human's* corrections are the durable part: the name they
-- fixed, the take they pulled out of a group, and which take is the keeper.
-- Hence a table rather than a derived view.
--
-- Nothing here reaches `songs`. A keeper is a producer's choice inside staging;
-- promoting one into the catalog is a later step with its own migration.

CREATE TABLE IF NOT EXISTS session_take_groups (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES recording_sessions(id) ON DELETE CASCADE,

    -- The name a producer set by hand. NULL means "show the guess", which is
    -- derived from the takes' own words at display time rather than frozen
    -- here — so a name is never stale, and the six-word rule lives in one place.
    name TEXT,

    -- The take the producer picked to keep. No default and nullable on purpose:
    -- a group starts with no keeper and the product must not choose one
    -- (SESS-15). ON DELETE SET NULL because deleting a take must not delete the
    -- group its siblings are in.
    keeper_take_id INTEGER REFERENCES session_takes(id) ON DELETE SET NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_take_groups_session
    ON session_take_groups (session_id);

-- NULL is the normal state, not a defect: a take the guess cannot confidently
-- assign to a song stays visible on its own (SESS-14).
ALTER TABLE session_takes
    ADD COLUMN IF NOT EXISTS group_id INTEGER
        REFERENCES session_take_groups(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_session_takes_group ON session_takes (group_id);

COMMENT ON TABLE session_take_groups IS
    'Takes judged to be attempts at one song, plus the producer''s corrections.';
COMMENT ON COLUMN session_take_groups.keeper_take_id IS
    'The take the producer chose to keep; NULL until a human chooses (SESS-15).';
COMMENT ON COLUMN session_takes.group_id IS
    'The group this take was assigned to, or NULL when it stands on its own.';
