-- Migration 19: combined_embedding back to the 549 dimensions the code produces
-- (issue #111).
--
-- create_combined_embedding() concatenates 37 librosa dimensions with CLAP's 512,
-- so a complete audio representation is 549 wide, and search_by_embedding()'s own
-- docstring still says so. init/03-add-audio-embeddings.sql declared the column
-- that way; migration 04 re-created the table at vector(512) while moving song_id
-- to an integer. Nothing complained for ten months because CLAP had never produced
-- a vector to store -- clap_embedding was NULL for all 1,415 rows and every
-- combined_embedding was the 512-dimensional librosa fallback. With the CLAP path
-- fixed, a complete row no longer fits the column.
--
-- pgvector cannot cast a vector(512) to a vector(549), and every value has to be
-- rebuilt from the audio anyway, so the column is cleared first. Until
-- scripts/reindex_audio_embeddings.py refills it, a NULL row is simply absent from
-- audio-similarity results -- the search functions compare
-- `1 - (embedding <=> query) >= threshold`, which drops NULL -- rather than being
-- compared against a different kind of representation (CAT-11).
--
-- Guarded on the column's current dimension so a second run is a no-op: re-running
-- the UPDATE unconditionally would wipe the vectors the re-index had just built.

DO $$
BEGIN
    IF (
        SELECT atttypmod
        FROM pg_attribute
        WHERE attrelid = 'audio_embeddings'::regclass
          AND attname = 'combined_embedding'
    ) <> 549 THEN
        UPDATE audio_embeddings SET combined_embedding = NULL;
        ALTER TABLE audio_embeddings
            ALTER COLUMN combined_embedding TYPE vector(549);
        RAISE NOTICE 'combined_embedding widened to vector(549) and cleared; run scripts/reindex_audio_embeddings.py';
    ELSE
        RAISE NOTICE 'combined_embedding is already vector(549), nothing to do';
    END IF;
END $$;
