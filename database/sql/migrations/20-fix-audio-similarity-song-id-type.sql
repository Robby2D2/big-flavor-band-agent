-- Migration 20: search_similar_songs_by_audio returns songs.id as it is (issue #111).
--
-- Migration 04 moved song_id from a string to an integer across every table, but
-- the search functions' RETURNS TABLE declarations were never updated with it --
-- they still declare `song_id VARCHAR(50)` while `songs.id` is an integer. plpgsql
-- checks that only when a row is actually returned, so the function raises
--
--     DatatypeMismatchError: structure of query does not match function result type
--     DETAIL: Returned type integer does not match expected type character varying
--             in column 1.
--
-- on any non-empty result. Audio-similarity search has therefore been answering
-- HTTP 500 since migration 04, not merely ranking on the librosa fallback --
-- /api/search/audio and /api/songs/{id}/related both go through this function.
-- Found while verifying the CLAP re-index, because #111's acceptance criteria ask
-- that audio-similarity search actually answer for any catalog song.
--
-- Only the declared type of column 1 changes. The body, the ordering and the
-- similarity expression are byte-for-byte what was live, so this fixes the error
-- without touching how results are ranked.
--
-- The same latent defect is in search_by_tempo_and_audio, search_songs_hybrid and
-- search_similar_songs_by_text. They belong to the tempo, hybrid and text modes
-- that issue #111 puts out of scope, so they are reported rather than changed here.

-- CREATE OR REPLACE cannot change a function's return type ("Row type defined by
-- OUT parameters is different"), so the old signature is dropped first.
DROP FUNCTION IF EXISTS search_similar_songs_by_audio(vector, INTEGER, FLOAT);

CREATE OR REPLACE FUNCTION search_similar_songs_by_audio(
    query_embedding vector,
    limit_count INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.0
)
RETURNS TABLE (
    song_id INTEGER,
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
)
LANGUAGE plpgsql
AS $function$
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
$function$;
