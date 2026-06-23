-- Migration 08: user-facing version name for song_versions (issue #43)
--
-- The /produce versions manager lets a producer rename any version. `label` is a
-- type discriminator ('original' / 'cleaned') and is too small/semantic to reuse
-- as a display name, so add a separate nullable `name`. When NULL the API derives
-- a sensible default from `label`, so existing rows keep displaying correctly.

ALTER TABLE song_versions
    ADD COLUMN IF NOT EXISTS name VARCHAR(120);

COMMENT ON COLUMN song_versions.name IS
    'Optional producer-assigned display name for the version; NULL falls back to a label-derived default.';
