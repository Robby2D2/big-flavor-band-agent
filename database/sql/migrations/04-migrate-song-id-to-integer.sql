-- Migration: Change song ID from VARCHAR to INTEGER
-- This migration converts the song ID to use numeric IDs from audio URLs

-- Step 1: Create temporary table with new schema
CREATE TABLE songs_new (
    id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    genre VARCHAR(100),
    tempo_bpm FLOAT,
    key VARCHAR(20),
    duration_seconds INTEGER,
    energy VARCHAR(20),
    mood VARCHAR(50),
    recording_date DATE,
    audio_quality VARCHAR(20),
    audio_url TEXT,
    rating INTEGER CHECK (rating >= 0 AND rating <= 5),
    session VARCHAR(100),
    uploaded_on TIMESTAMP,
    recorded_on DATE,
    is_original BOOLEAN DEFAULT FALSE,
    track_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Migrate data (only if you have existing data with numeric IDs)
-- Note: This assumes old IDs can be converted or you have audio URLs with numeric IDs
-- If starting fresh, skip this step

-- INSERT INTO songs_new (id, title, genre, tempo_bpm, key, duration_seconds, energy, mood, 
--                        recording_date, audio_quality, audio_url, rating, session, uploaded_on, 
--                        recorded_on, is_original, track_number, created_at, updated_at)
-- SELECT 
--     CAST(REGEXP_REPLACE(audio_url, '.*/audio/(\d+)/.*', '\1') AS INTEGER) as id,
--     title, genre, tempo_bpm, key, duration_seconds, energy, mood,
--     recording_date, audio_quality, audio_url, rating, session, uploaded_on,
--     recorded_on, is_original, track_number, created_at, updated_at
-- FROM songs
-- WHERE audio_url ~ '/audio/\d+/';

-- Step 3: Drop old tables that depend on songs
DROP TABLE IF EXISTS audio_analysis CASCADE;
DROP TABLE IF EXISTS song_embeddings CASCADE;
DROP TABLE IF EXISTS song_comments CASCADE;
DROP TABLE IF EXISTS song_instruments CASCADE;
DROP TABLE IF EXISTS audio_embeddings CASCADE;
DROP TABLE IF EXISTS text_embeddings CASCADE;

-- Step 4: Drop old songs table
DROP TABLE IF EXISTS songs CASCADE;

-- Step 5: Rename new table
ALTER TABLE songs_new RENAME TO songs;

-- Step 6: Recreate dependent tables with INTEGER foreign keys

-- Audio analysis results
CREATE TABLE audio_analysis (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    audio_url TEXT NOT NULL,
    bpm FLOAT,
    key VARCHAR(20),
    energy FLOAT,
    danceability FLOAT,
    valence FLOAT,
    acousticness FLOAT,
    instrumentalness FLOAT,
    liveness FLOAT,
    speechiness FLOAT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(audio_url)
);

-- Embeddings for RAG (using pgvector)
CREATE TABLE song_embeddings (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    content_type VARCHAR(50) NOT NULL, -- 'metadata', 'lyrics', 'description'
    content TEXT NOT NULL,
    embedding vector(1536), -- OpenAI embeddings dimension
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Comments table
CREATE TABLE song_comments (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL,
    author VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Song_instruments junction table
CREATE TABLE song_instruments (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    musician_id INTEGER REFERENCES musicians(id) ON DELETE CASCADE,
    instrument_id INTEGER REFERENCES instruments(id) ON DELETE CASCADE,
    UNIQUE(song_id, musician_id, instrument_id)
);

-- Audio embeddings table
CREATE TABLE audio_embeddings (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    audio_path TEXT NOT NULL,
    combined_embedding vector(512),
    clap_embedding vector(512),
    librosa_features JSONB,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(audio_path)
);

-- Text embeddings table
CREATE TABLE text_embeddings (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    content_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    text_embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(song_id, content_type)
);

-- Recreate indexes
CREATE INDEX idx_songs_genre ON songs(genre);
CREATE INDEX idx_songs_tempo ON songs(tempo_bpm);
CREATE INDEX idx_songs_energy ON songs(energy);
CREATE INDEX idx_songs_session ON songs(session);
CREATE INDEX idx_songs_rating ON songs(rating);
CREATE INDEX idx_songs_is_original ON songs(is_original);

CREATE INDEX idx_audio_analysis_song_id ON audio_analysis(song_id);
CREATE INDEX idx_song_embeddings_song_id ON song_embeddings(song_id);
CREATE INDEX idx_song_comments_song_id ON song_comments(song_id);
CREATE INDEX idx_song_instruments_song_id ON song_instruments(song_id);
CREATE INDEX idx_song_instruments_musician_id ON song_instruments(musician_id);
CREATE INDEX idx_song_instruments_instrument_id ON song_instruments(instrument_id);
CREATE INDEX idx_audio_embeddings_song_id ON audio_embeddings(song_id);
CREATE INDEX idx_text_embeddings_song_id ON text_embeddings(song_id);

-- Vector similarity search indexes
CREATE INDEX ON song_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON audio_embeddings USING ivfflat (combined_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON text_embeddings USING ivfflat (text_embedding vector_cosine_ops) WITH (lists = 100);

-- Trigger for songs table
CREATE TRIGGER update_songs_updated_at BEFORE UPDATE ON songs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for song_comments table
CREATE TRIGGER update_song_comments_updated_at BEFORE UPDATE ON song_comments
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
