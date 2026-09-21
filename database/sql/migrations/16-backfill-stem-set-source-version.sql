-- Attribute legacy stem sets to the version they were actually separated from.
--
-- `song_stem_sets.source_version_id` was added after the first sets existed, so
-- the earliest rows carry NULL. Before this, nothing read the column — the UI
-- simply showed a song's newest complete set whatever version was selected — so
-- the NULLs were harmless. Now that the console only shows stems belonging to
-- the selected version, a NULL set would be shown for no version at all, and a
-- song with perfectly good stems on disk would look unseparated.
--
-- A NULL set was started by POST /api/produce/stems/separate with no
-- source_version_id, which resolves to the catalog original
-- (_resolve_clean_source_path). The song's `original`-labelled version points at
-- that same file, so that version is the correct owner.
--
-- Idempotent: only fills NULLs, and only where exactly one original-labelled
-- version exists to attribute them to. Anything ambiguous is deliberately left
-- NULL — an unattributed set is better than a wrongly attributed one, and the
-- producer can re-separate.
UPDATE song_stem_sets s
SET source_version_id = v.id
FROM (
    SELECT song_id, MIN(id) AS id, COUNT(*) AS n
    FROM song_versions
    WHERE label = 'original'
    GROUP BY song_id
    HAVING COUNT(*) = 1
) v
WHERE s.source_version_id IS NULL
  AND s.song_id = v.song_id;
