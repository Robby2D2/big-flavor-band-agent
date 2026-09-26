-- Migration 18: recording-session import — find the songs inside a rehearsal
--
-- The band leaves Reaper recording for a whole session and uploads the project
-- as a zip: a WavPack file per instrument channel plus the .RPP. This schema
-- stages what the scan finds so a producer can review it.
--
-- Nothing here touches `songs`. Session material is deliberately staged outside
-- the catalog: detection is fallible (a stretch of talking can read as a song),
-- so a human confirms before anything becomes catalog data. Importing a take
-- into `songs`/`song_versions` is a later step and gets its own migration.

-- One uploaded session.
CREATE TABLE IF NOT EXISTS recording_sessions (
    id SERIAL PRIMARY KEY,

    -- Display name, taken from the zip's folder name ("20260501 May the Farts
    -- Be With You"), which is also where recorded_on comes from.
    name TEXT NOT NULL,
    source_filename TEXT,
    recorded_on DATE,

    -- Background-job lifecycle, same shape as song_stem_sets.status so a
    -- producer polling can always tell a failure from a slow run:
    -- 'uploading' | 'queued' | 'running' | 'complete' | 'failed'.
    status VARCHAR(16) NOT NULL DEFAULT 'uploading',

    -- Which part of the pipeline is running ('unpacking', 'scanning',
    -- 'transcribing', 'rendering'), and how far through it is (0-100). Durable
    -- rather than in-memory because a scan outlives a request by many minutes
    -- and a reload mid-run has to pick the story back up.
    stage VARCHAR(32),
    progress SMALLINT NOT NULL DEFAULT 0,
    error TEXT,

    -- Absolute container path to the unpacked material. Cleared when the raw
    -- WavPack is purged, which is why it is nullable.
    raw_dir TEXT,

    -- Which Reaper RECPASS values this upload actually carried media for. A
    -- project accumulates many nights, so most of its passes belong to earlier
    -- sessions and are not in this zip.
    rec_passes INTEGER[],

    sample_rate INTEGER,
    duration_seconds INTEGER,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recording_sessions_created
    ON recording_sessions (created_at DESC);

-- One channel of the recording, as Reaper named it.
CREATE TABLE IF NOT EXISTS session_tracks (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES recording_sessions(id) ON DELETE CASCADE,

    -- The band's own track name ("4 Kev Vox", "7 DRUM Mic").
    name TEXT NOT NULL,
    source_name TEXT NOT NULL,

    -- The Demucs-style bucket the name maps to (vocals/drums/bass/guitar/
    -- piano/other), so session stems carry the names the audio tools resolve.
    role VARCHAR(16) NOT NULL,

    rec_pass INTEGER,

    -- Timeline position in seconds. Tracks within one pass do NOT share a
    -- start: a player who arms late is offset by minutes, measured at +145s on
    -- one guitar track, so this is the only truth about alignment.
    position_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,

    -- Peak level in dBFS. Half the tracks in a real project are automation or
    -- folder tracks holding no audio; those are recorded here as dead rather
    -- than dropped, so the producer can see what was in the upload.
    peak_db REAL,
    is_dead BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_session_tracks_session ON session_tracks (session_id);

-- One attempt at a song: a stretch the band played, bounded by them stopping.
CREATE TABLE IF NOT EXISTS session_takes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES recording_sessions(id) ON DELETE CASCADE,

    rec_pass INTEGER,

    -- Bounds on the session timeline, in seconds.
    start_seconds DOUBLE PRECISION NOT NULL,
    end_seconds DOUBLE PRECISION NOT NULL,

    -- The words sung during the take, from Whisper over the vocal tracks.
    -- Empty for an instrumental, which is a real answer.
    transcript TEXT,

    -- Absolute container path to the take's summed mix.
    mix_path TEXT,

    -- Drawing envelope for the mix, same shape and purpose as
    -- song_versions.waveform_peaks (migration 12): a few KB of JSON instead of
    -- shipping the audio to the browser to draw it.
    waveform_peaks JSONB,

    -- A producer can set this aside without deleting it — a fragment, or a
    -- stretch of talking detection mistook for a song.
    excluded BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_takes_session
    ON session_takes (session_id, start_seconds);

-- One track's audio for one take. These ARE the stems: the band recorded the
-- channels apart, so nothing needs separating.
CREATE TABLE IF NOT EXISTS session_take_stems (
    id SERIAL PRIMARY KEY,
    take_id INTEGER NOT NULL REFERENCES session_takes(id) ON DELETE CASCADE,
    track_id INTEGER REFERENCES session_tracks(id) ON DELETE SET NULL,

    -- Unique within the take ('vocals', 'vocals-2', ...) because two singers
    -- each have a mic and a stem set keys on this name.
    name VARCHAR(32) NOT NULL,

    -- The band's own track name, for display over the bucket name.
    display_name TEXT,

    path TEXT NOT NULL,
    peak_db REAL,
    waveform_peaks JSONB,

    UNIQUE (take_id, name)
);

CREATE INDEX IF NOT EXISTS idx_session_take_stems_take ON session_take_stems (take_id);

COMMENT ON TABLE recording_sessions IS
    'One uploaded Reaper rehearsal session, with the lifecycle of its scan.';
COMMENT ON TABLE session_tracks IS
    'The channels of a recording session, positioned on its timeline.';
COMMENT ON TABLE session_takes IS
    'Detected attempts at songs, staged for review; never catalog data.';
COMMENT ON TABLE session_take_stems IS
    'Per-track audio for one take — already separated, so no Demucs needed.';
