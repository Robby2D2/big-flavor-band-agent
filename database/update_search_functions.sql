-- Migration to add all song fields to search functions
-- Run this to update existing database functions

-- Drop existing functions first to allow return type changes
DROP FUNCTION IF EXISTS search_similar_songs_by_audio(vector, integer, double precision);
DROP FUNCTION IF EXISTS search_by_tempo_and_audio(double precision, double precision, vector, integer);
DROP FUNCTION IF EXISTS search_songs_hybrid(vector, vector, double precision, double precision, integer);

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
