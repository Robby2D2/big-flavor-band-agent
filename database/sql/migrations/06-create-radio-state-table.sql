-- Externalize runtime radio state so it survives backend restarts and is shared
-- across backend instances (issue #2). State previously lived in per-process
-- in-memory dicts in backend_api.py.

-- Single-row table holding the live radio state (current song, queue, play/pause,
-- position). id is pinned to 1 so there is always exactly one row.
CREATE TABLE IF NOT EXISTS radio_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT radio_state_single_row CHECK (id = 1)
);

-- Active listeners, tracked cross-process with a last-ping timestamp so the
-- reported count is consistent across backend instances and TTL cleanup works.
CREATE TABLE IF NOT EXISTS radio_listeners (
    listener_id VARCHAR(255) PRIMARY KEY,
    last_ping TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_radio_listeners_last_ping ON radio_listeners(last_ping);
