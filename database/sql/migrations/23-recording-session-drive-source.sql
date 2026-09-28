-- Migration 23: remember which Google Drive folder a recording session came from.
--
-- The band's Reaper projects already live in a shared Drive folder, so a session
-- can be imported from there instead of being zipped, downloaded and uploaded
-- again through the browser. The folder id is what lets the import list show
-- which sessions have already been brought in.
--
-- NULL for a session uploaded as a zip. Unique where set, so two clicks (or two
-- producers) cannot scan the same folder twice; deleting the session frees the
-- folder to be imported again.

ALTER TABLE recording_sessions
    ADD COLUMN IF NOT EXISTS drive_folder_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_recording_sessions_drive_folder
    ON recording_sessions (drive_folder_id)
    WHERE drive_folder_id IS NOT NULL;
