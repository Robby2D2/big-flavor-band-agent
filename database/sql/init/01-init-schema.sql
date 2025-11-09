-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm extension for text similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Songs table
CREATE TABLE songs (
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

-- Sessions table (for session names)
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Musicians table
CREATE TABLE musicians (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Instruments table
CREATE TABLE instruments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
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

-- Document chunks for RAG
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    source VARCHAR(255) NOT NULL, -- filename or URL
    content TEXT NOT NULL,
    metadata JSONB,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
-- Text embeddings table
CREATE TABLE text_embeddings (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
    content_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(song_id, content_type)
);

-- Create indexes
CREATE INDEX idx_songs_genre ON songs(genre);
CREATE INDEX idx_songs_tempo ON songs(tempo_bpm);
CREATE INDEX idx_songs_energy ON songs(energy);
CREATE INDEX idx_audio_analysis_song_id ON audio_analysis(song_id);
CREATE INDEX idx_song_embeddings_song_id ON song_embeddings(song_id);

-- Create vector similarity search indexes
CREATE INDEX ON song_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for songs table
CREATE TRIGGER update_songs_updated_at BEFORE UPDATE ON songs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
