-- Migration 10: name what's actually in each stem.
--
-- Demucs' source list is fixed by the model weights (htdemucs_6s emits exactly
-- vocals/drums/bass/guitar/piano/other), so a banjo, mandolin or fiddle ends up
-- inside "other" — present in the audio, but unnamed. Rather than trying to
-- separate instruments the model was never trained on, we label each stem with
-- an AudioSet tagger and let a producer override that label by hand.
--
-- Nothing here changes how stems are produced or stored: song_stems.name stays
-- the Demucs source name and path stays the file on disk.

-- Producer's own label for a stem ("Banjo" on the stem Demucs called "other").
-- NULL means fall back to song_stems.name.
ALTER TABLE song_stems ADD COLUMN IF NOT EXISTS display_name VARCHAR(64);

-- Detected instruments, as
--   {"instruments": [{"label": "Banjo", "score": 0.72}, ...],
--    "silent": false,
--    "model": "MIT/ast-finetuned-audioset-10-10-0.4593"}
-- "silent" is a real answer, not a failure: a band with no piano still gets a
-- piano stem out of Demucs, and it's worth saying that it came back empty.
ALTER TABLE song_stems ADD COLUMN IF NOT EXISTS instrument_tags JSONB;

-- When tagging last ran, so a NULL tag payload can be told apart from "never
-- tagged" once a stem has been through a tagger that recognised nothing.
ALTER TABLE song_stems ADD COLUMN IF NOT EXISTS tagged_at TIMESTAMP;

COMMENT ON COLUMN song_stems.display_name IS
    'Producer-facing label overriding the Demucs source name; NULL falls back to name.';
COMMENT ON COLUMN song_stems.instrument_tags IS
    'AudioSet instrument tagging for this stem: {instruments:[{label,score}], silent, model}.';
