-- Migration 22: retire three search functions nothing calls (issue #114).
--
-- Migration 04 moved song_id from a string to an integer, but these three still
-- declare `song_id VARCHAR(50)` in their RETURNS TABLE, and two of them also
-- reference `te.text_embedding`, a column that no longer exists (text embeddings
-- moved to all-MiniLM-L6-v2, so the column is `embedding` at 384 dims). Every
-- call raises -- 42804 for the tempo function, 42703 for the two text-side ones.
-- Postgres validates the tuple descriptor upfront, so an empty result raises too;
-- there is no "works until it matches something" behaviour.
--
-- They are retired rather than repaired because nothing reaches them: their only
-- callers were three SongRAGSystem methods that had no callers of their own, and
-- each mode SRCH-02 promises is served by a different, working path -- text by
-- search_by_text_description, lyric by search_lyrics_by_keyword, tempo by
-- search_by_tempo_range, hybrid by search_text_with_tempo, audio similarity by
-- search_similar_songs_by_audio (which migration 20 fixed and this leaves alone).
-- Repairing three unreachable functions would be speculative code; the owner's
-- call on 2026-09-28 was to delete them and add them back if they are ever wanted.
--
-- Dropped by signature, because these names must go from pg_proc: an unreachable
-- function that raises unconditionally is exactly the schema drift this removes.
-- The init/03 definitions stay as the historical record of the original schema.

DROP FUNCTION IF EXISTS search_by_tempo_and_audio(double precision, double precision, vector, integer);
DROP FUNCTION IF EXISTS search_songs_hybrid(vector, vector, double precision, double precision, integer);
DROP FUNCTION IF EXISTS search_similar_songs_by_text(vector, integer, character varying[]);
