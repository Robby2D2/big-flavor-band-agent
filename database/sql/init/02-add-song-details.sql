-- Add additional columns for song details from web scraping

-- Add new columns to songs table
ALTER TABLE songs 
ADD COLUMN IF NOT EXISTS rating INTEGER CHECK (rating >= 0 AND rating <= 5),
ADD COLUMN IF NOT EXISTS session VARCHAR(100),
ADD COLUMN IF NOT EXISTS uploaded_on TIMESTAMP,
ADD COLUMN IF NOT EXISTS recorded_on DATE,
ADD COLUMN IF NOT EXISTS is_original BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS track_number INTEGER;

-- Create sessions table for better normalization
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create comments table
CREATE TABLE IF NOT EXISTS song_comments (
    id SERIAL PRIMARY KEY,
    song_id VARCHAR(50) REFERENCES songs(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL,
    author VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create instruments table
CREATE TABLE IF NOT EXISTS instruments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Create musicians table
CREATE TABLE IF NOT EXISTS musicians (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Create song_instruments junction table (who played what on which song)
CREATE TABLE IF NOT EXISTS song_instruments (
    id SERIAL PRIMARY KEY,
    song_id VARCHAR(50) REFERENCES songs(id) ON DELETE CASCADE,
    musician_id INTEGER REFERENCES musicians(id) ON DELETE CASCADE,
    instrument_id INTEGER REFERENCES instruments(id) ON DELETE CASCADE,
    UNIQUE(song_id, musician_id, instrument_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_songs_session ON songs(session);
CREATE INDEX IF NOT EXISTS idx_songs_rating ON songs(rating);
CREATE INDEX IF NOT EXISTS idx_songs_is_original ON songs(is_original);
CREATE INDEX IF NOT EXISTS idx_song_comments_song_id ON song_comments(song_id);
CREATE INDEX IF NOT EXISTS idx_song_instruments_song_id ON song_instruments(song_id);
CREATE INDEX IF NOT EXISTS idx_song_instruments_musician_id ON song_instruments(musician_id);
CREATE INDEX IF NOT EXISTS idx_song_instruments_instrument_id ON song_instruments(instrument_id);

-- Trigger for song_comments table
CREATE TRIGGER update_song_comments_updated_at BEFORE UPDATE ON song_comments
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
