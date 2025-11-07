-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm extension for text similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Songs table
CREATE TABLE songs (
    id VARCHAR(50) PRIMARY KEY,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audio analysis results
CREATE TABLE audio_analysis (
    id SERIAL PRIMARY KEY,
    song_id VARCHAR(50) REFERENCES songs(id) ON DELETE CASCADE,
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
    song_id VARCHAR(50) REFERENCES songs(id) ON DELETE CASCADE,
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
