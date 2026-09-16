-- Multi-label mood and genre.
--
-- songs.mood and songs.genre hold exactly one value each, because the derive
-- scripts ask the model to "choose exactly one". That makes a compound question
-- unanswerable: a song cannot be both melancholic and calm, so "which songs are
-- about water and feel calm" can only ever match on one half.
--
-- These are additive. The single columns stay as the song's primary label (the
-- UI badges, the existing filters); this table carries every label that applies,
-- seeded from those columns so nothing is lost.
CREATE TABLE IF NOT EXISTS song_tags (
    id SERIAL PRIMARY KEY,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    kind VARCHAR(20) NOT NULL,          -- 'mood' | 'genre'
    value VARCHAR(50) NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'derived',  -- 'primary' | 'derived'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (song_id, kind, value)
);

CREATE INDEX IF NOT EXISTS idx_song_tags_song_id ON song_tags(song_id);
-- "every song tagged calm", which is what the keyword branch asks.
CREATE INDEX IF NOT EXISTS idx_song_tags_kind_value ON song_tags(kind, value);
