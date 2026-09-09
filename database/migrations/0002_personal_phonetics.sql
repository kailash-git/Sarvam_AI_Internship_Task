-- 0002_personal_phonetics: accent-adaptive ("personal") phonetics.
--
-- Kivi learns HOW THIS PERSON's ASR systematically mangles sounds, from their own
-- corrections, and uses that to nominate/rank candidates that a generic phonetic
-- algorithm would miss. This is the "personal" in "personal phonetic memory".

-- One learned sound-substitution rule in the user's accent profile.
-- Derived by aligning a misheard surface (what ASR wrote) with the chosen form
-- (what the user meant) and coalescing the edit into src -> dst chunks.
CREATE TABLE sound_pattern (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    position     TEXT NOT NULL,              -- onset | medial | coda
    src          TEXT NOT NULL DEFAULT '',   -- grapheme chunk ASR produced ('' = insertion)
    dst          TEXT NOT NULL DEFAULT '',   -- grapheme chunk the user meant ('' = deletion)
    observations INTEGER NOT NULL DEFAULT 0, -- how many correction pairs produced this rule
    weight       REAL NOT NULL DEFAULT 0.0,  -- derived: saturating f(observations), in [0,1]
    origin       TEXT NOT NULL DEFAULT 'learned',  -- seed | learned
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_sound_pattern_key ON sound_pattern(position, src, dst);
CREATE INDEX idx_sound_pattern_obs ON sound_pattern(observations);

-- Decision-level explainability for the personal-phonetics contribution.
ALTER TABLE decision ADD COLUMN s_personal    REAL DEFAULT 0.0;
ALTER TABLE decision ADD COLUMN personal_note TEXT;
