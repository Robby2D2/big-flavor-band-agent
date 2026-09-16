-- Verse-sized lyric chunks for semantic search.
--
-- Until this existed, a song's whole lyric — 850 characters on average, up to
-- 7,863 — was averaged into ONE 384-dimension vector. A song that mentions the
-- ocean once was diluted past the point of being findable, which is why a
-- semantic search for "the ocean" missed three songs called "Down by the River".
--
-- The lyric *text* stays in text_embeddings (content_type 'lyrics') as the
-- single source of truth; these are a derived search index, the same
-- relationship song_lyric_timings has to it. Dropping and rebuilding this table
-- loses nothing but the time to re-embed.
CREATE TABLE IF NOT EXISTS song_lyric_chunks (
    id SERIAL PRIMARY KEY,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (song_id, chunk_index)
);

-- Rolling chunk hits back up to their songs.
CREATE INDEX IF NOT EXISTS idx_song_lyric_chunks_song_id ON song_lyric_chunks(song_id);
