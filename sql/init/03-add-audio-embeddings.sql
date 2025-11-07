-- Add audio embeddings support for RAG system
-- This schema supports multi-modal audio search using librosa + CLAP embeddings

-- Audio embeddings table - stores vector representations of songs
CREATE TABLE IF NOT EXISTS audio_embeddings (
    id SERIAL PRIMARY KEY,
    song_id VARCHAR(50) REFERENCES songs(id) ON DELETE CASCADE,
    audio_path TEXT NOT NULL,
    
    -- Combined embedding for vector similarity search
    -- 549 dimensions: 37 (librosa features) + 512 (CLAP embedding)
    combined_embedding vector(549),
    
    -- Store individual components for analysis
    clap_embedding vector(512),  -- Deep learning audio embedding
    
    -- Librosa features as JSON for reference
    librosa_features JSONB,
    
    -- Metadata
    embedding_model VARCHAR(100) DEFAULT 'clap-htsat-unfused',
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure one embedding per audio file
    UNIQUE(audio_path)
);

-- Text embeddings table - for lyrics, descriptions, metadata RAG
-- This complements audio embeddings for multimodal search
CREATE TABLE IF NOT EXISTS text_embeddings (
    id SERIAL PRIMARY KEY,
    song_id VARCHAR(50) REFERENCES songs(id) ON DELETE CASCADE,
    
    -- Text content and type
    content_type VARCHAR(50) NOT NULL, -- 'title', 'genre', 'description', 'lyrics', 'tags'
    content TEXT NOT NULL,
    
    -- OpenAI or other text embedding (default 1536 dims for OpenAI)
    text_embedding vector(1536),
    
    -- Metadata
    embedding_model VARCHAR(100) DEFAULT 'text-embedding-ada-002',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Allow multiple text embeddings per song (different content types)
    UNIQUE(song_id, content_type)
);

-- Multimodal search results cache - stores hybrid search results
CREATE TABLE IF NOT EXISTS search_cache (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) UNIQUE NOT NULL,  -- Hash of query parameters
    query_text TEXT,
    query_type VARCHAR(50),  -- 'audio', 'text', 'hybrid'
    
    -- Results as JSONB array
    results JSONB NOT NULL,
    
    -- Cache metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 0
);

-- Indexes for vector similarity search
-- Using IVFFlat for approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS idx_audio_embeddings_combined 
    ON audio_embeddings USING ivfflat (combined_embedding vector_cosine_ops) 
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_audio_embeddings_clap 
    ON audio_embeddings USING ivfflat (clap_embedding vector_cosine_ops) 
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_text_embeddings_vector 
    ON text_embeddings USING ivfflat (text_embedding vector_cosine_ops) 
    WITH (lists = 100);

-- Indexes for lookups
CREATE INDEX IF NOT EXISTS idx_audio_embeddings_song_id ON audio_embeddings(song_id);
CREATE INDEX IF NOT EXISTS idx_audio_embeddings_audio_path ON audio_embeddings(audio_path);
CREATE INDEX IF NOT EXISTS idx_text_embeddings_song_id ON text_embeddings(song_id);
CREATE INDEX IF NOT EXISTS idx_text_embeddings_content_type ON text_embeddings(content_type);
CREATE INDEX IF NOT EXISTS idx_search_cache_query_hash ON search_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_search_cache_expires_at ON search_cache(expires_at);

-- Create GIN index on librosa_features for JSON queries
CREATE INDEX IF NOT EXISTS idx_audio_embeddings_librosa_features 
    ON audio_embeddings USING gin (librosa_features);

-- Function to search similar songs by audio embedding
CREATE OR REPLACE FUNCTION search_similar_songs_by_audio(
    query_embedding vector(549),
    limit_count INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.0
)
RETURNS TABLE (
    song_id VARCHAR(50),
    title VARCHAR(255),
    genre VARCHAR(100),
    tempo_bpm FLOAT,
    audio_path TEXT,
    similarity FLOAT,
    librosa_features JSONB,
    rating INTEGER,
    session VARCHAR(100),
    uploaded_on TIMESTAMP,
    recorded_on DATE,
    is_original BOOLEAN,
    track_number INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.title,
        s.genre,
        s.tempo_bpm,
        ae.audio_path,
        1 - (ae.combined_embedding <=> query_embedding) AS similarity,
        ae.librosa_features,
        s.rating,
        s.session,
        s.uploaded_on,
        s.recorded_on,
        s.is_original,
        s.track_number
    FROM audio_embeddings ae
    JOIN songs s ON ae.song_id = s.id
    WHERE 1 - (ae.combined_embedding <=> query_embedding) >= similarity_threshold
    ORDER BY ae.combined_embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Function to search similar songs by text embedding
CREATE OR REPLACE FUNCTION search_similar_songs_by_text(
    query_embedding vector(1536),
    limit_count INTEGER DEFAULT 10,
    content_types VARCHAR(50)[] DEFAULT ARRAY['title', 'genre', 'description', 'tags']
)
RETURNS TABLE (
    song_id VARCHAR(50),
    title VARCHAR(255),
    content_type VARCHAR(50),
    content TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        te.song_id,
        s.title,
        te.content_type,
        te.content,
        1 - (te.text_embedding <=> query_embedding) AS similarity
    FROM text_embeddings te
    JOIN songs s ON te.song_id = s.id
    WHERE te.content_type = ANY(content_types)
    ORDER BY te.text_embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Function for hybrid search (audio + text)
CREATE OR REPLACE FUNCTION search_songs_hybrid(
    audio_query_embedding vector(549),
    text_query_embedding vector(1536),
    audio_weight FLOAT DEFAULT 0.6,
    text_weight FLOAT DEFAULT 0.4,
    limit_count INTEGER DEFAULT 10
)
RETURNS TABLE (
    song_id VARCHAR(50),
    title VARCHAR(255),
    genre VARCHAR(100),
    combined_score FLOAT,
    audio_similarity FLOAT,
    text_similarity FLOAT,
    rating INTEGER,
    session VARCHAR(100),
    uploaded_on TIMESTAMP,
    recorded_on DATE,
    is_original BOOLEAN,
    track_number INTEGER,
    tempo_bpm FLOAT,
    audio_path TEXT,
    librosa_features JSONB
) AS $$
BEGIN
    RETURN QUERY
    WITH audio_scores AS (
        SELECT 
            ae.song_id,
            1 - (ae.combined_embedding <=> audio_query_embedding) AS audio_sim,
            ae.audio_path,
            ae.librosa_features
        FROM audio_embeddings ae
    ),
    text_scores AS (
        SELECT 
            te.song_id,
            MAX(1 - (te.text_embedding <=> text_query_embedding)) AS text_sim
        FROM text_embeddings te
        GROUP BY te.song_id
    )
    SELECT 
        s.id,
        s.title,
        s.genre,
        (COALESCE(a.audio_sim, 0) * audio_weight + COALESCE(t.text_sim, 0) * text_weight) AS combined_score,
        COALESCE(a.audio_sim, 0) AS audio_similarity,
        COALESCE(t.text_sim, 0) AS text_similarity,
        s.rating,
        s.session,
        s.uploaded_on,
        s.recorded_on,
        s.is_original,
        s.track_number,
        s.tempo_bpm,
        a.audio_path,
        a.librosa_features
    FROM songs s
    LEFT JOIN audio_scores a ON s.id = a.song_id
    LEFT JOIN text_scores t ON s.id = t.song_id
    WHERE COALESCE(a.audio_sim, 0) > 0 OR COALESCE(t.text_sim, 0) > 0
    ORDER BY combined_score DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get songs within tempo range with audio similarity
CREATE OR REPLACE FUNCTION search_by_tempo_and_audio(
    target_tempo FLOAT,
    tempo_tolerance FLOAT DEFAULT 10.0,
    query_embedding vector(549) DEFAULT NULL,
    limit_count INTEGER DEFAULT 10
)
RETURNS TABLE (
    song_id VARCHAR(50),
    title VARCHAR(255),
    tempo_bpm FLOAT,
    tempo_diff FLOAT,
    audio_similarity FLOAT,
    genre VARCHAR(100),
    rating INTEGER,
    session VARCHAR(100),
    uploaded_on TIMESTAMP,
    recorded_on DATE,
    is_original BOOLEAN,
    track_number INTEGER,
    audio_path TEXT,
    librosa_features JSONB
) AS $$
BEGIN
    IF query_embedding IS NULL THEN
        RETURN QUERY
        SELECT 
            s.id,
            s.title,
            s.tempo_bpm,
            ABS(s.tempo_bpm - target_tempo) AS tempo_diff,
            NULL::FLOAT AS audio_similarity,
            s.genre,
            s.rating,
            s.session,
            s.uploaded_on,
            s.recorded_on,
            s.is_original,
            s.track_number,
            NULL::TEXT AS audio_path,
            NULL::JSONB AS librosa_features
        FROM songs s
        WHERE s.tempo_bpm BETWEEN (target_tempo - tempo_tolerance) AND (target_tempo + tempo_tolerance)
        ORDER BY tempo_diff
        LIMIT limit_count;
    ELSE
        RETURN QUERY
        SELECT 
            s.id,
            s.title,
            s.tempo_bpm,
            ABS(s.tempo_bpm - target_tempo) AS tempo_diff,
            1 - (ae.combined_embedding <=> query_embedding) AS audio_similarity,
            s.genre,
            s.rating,
            s.session,
            s.uploaded_on,
            s.recorded_on,
            s.is_original,
            s.track_number,
            ae.audio_path,
            ae.librosa_features
        FROM songs s
        JOIN audio_embeddings ae ON s.id = ae.song_id
        WHERE s.tempo_bpm BETWEEN (target_tempo - tempo_tolerance) AND (target_tempo + tempo_tolerance)
        ORDER BY (tempo_diff / tempo_tolerance) + (1 - (1 - (ae.combined_embedding <=> query_embedding)))
        LIMIT limit_count;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- View to combine song metadata with embedding info
CREATE OR REPLACE VIEW songs_with_embeddings AS
SELECT 
    s.*,
    ae.id AS audio_embedding_id,
    ae.audio_path,
    ae.embedding_model AS audio_model,
    ae.extracted_at,
    ae.librosa_features,
    COUNT(DISTINCT te.id) AS text_embedding_count
FROM songs s
LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
LEFT JOIN text_embeddings te ON s.id = te.song_id
GROUP BY s.id, ae.id, ae.audio_path, ae.embedding_model, ae.extracted_at, ae.librosa_features;

-- Cleanup function for expired cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM search_cache
    WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE audio_embeddings IS 'Stores vector embeddings of audio files for similarity search';
COMMENT ON TABLE text_embeddings IS 'Stores vector embeddings of song metadata and text for multimodal search';
COMMENT ON TABLE search_cache IS 'Caches search results for performance optimization';
COMMENT ON FUNCTION search_similar_songs_by_audio IS 'Find songs with similar audio characteristics using vector similarity';
COMMENT ON FUNCTION search_similar_songs_by_text IS 'Find songs with similar text/metadata using vector similarity';
COMMENT ON FUNCTION search_songs_hybrid IS 'Hybrid search combining audio and text similarity with weighted scoring';
