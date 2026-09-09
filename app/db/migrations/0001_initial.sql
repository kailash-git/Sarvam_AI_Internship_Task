-- Kivi phonetic memory: initial schema.
-- Three transcript levels live in `utterances`; everything else supports the
-- learn -> store -> retrieve -> decide -> apply loop.

CREATE TABLE memory_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical         TEXT    NOT NULL,           -- the surface form the user wants to see
    category          TEXT    NOT NULL,           -- person | org | product | term | other
    phonetic_primary  TEXT    NOT NULL,           -- double-metaphone primary key of canonical
    phonetic_secondary TEXT   NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'candidate',  -- candidate | active | suppressed
    confidence        REAL    NOT NULL DEFAULT 0.0,          -- [0,1]
    source            TEXT    NOT NULL,           -- correction | dictionary | seed
    note              TEXT    NOT NULL DEFAULT '',
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (canonical, category)
);

CREATE INDEX idx_memory_phon_primary ON memory_entries (phonetic_primary);
CREATE INDEX idx_memory_status       ON memory_entries (status);

-- Observed spoken/ASR/mis-formatted forms that should map onto an entry.
CREATE TABLE aliases (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id       INTEGER NOT NULL REFERENCES memory_entries (id) ON DELETE CASCADE,
    surface_form   TEXT    NOT NULL,
    phonetic_key   TEXT    NOT NULL,
    observed_count INTEGER NOT NULL DEFAULT 1,
    last_seen      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (entry_id, surface_form)
);

CREATE INDEX idx_alias_phon  ON aliases (phonetic_key);
CREATE INDEX idx_alias_entry ON aliases (entry_id);

-- Raw evidence the product learned from. Never deleted (audit trail).
CREATE TABLE observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT    NOT NULL,   -- correction | dictionary | rejection | acceptance
    asr_text        TEXT    NOT NULL DEFAULT '',
    formatted_text  TEXT    NOT NULL DEFAULT '',
    corrected_text  TEXT    NOT NULL DEFAULT '',
    from_form       TEXT    NOT NULL DEFAULT '',   -- token/phrase before correction
    to_form         TEXT    NOT NULL DEFAULT '',   -- token/phrase after correction
    category        TEXT    NOT NULL DEFAULT '',
    entry_id        INTEGER REFERENCES memory_entries (id) ON DELETE SET NULL,
    raw_payload     TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_obs_entry ON observations (entry_id);
CREATE INDEX idx_obs_type  ON observations (type);

-- One row per candidate rewrite considered for an utterance (applied or not).
CREATE TABLE interventions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    utterance_id INTEGER REFERENCES utterances (id) ON DELETE CASCADE,
    entry_id     INTEGER REFERENCES memory_entries (id) ON DELETE SET NULL,
    span_text    TEXT    NOT NULL,
    from_text    TEXT    NOT NULL,
    to_text      TEXT    NOT NULL,
    applied      INTEGER NOT NULL,     -- 0 | 1
    score        REAL    NOT NULL,
    threshold    REAL    NOT NULL,
    reason_tag   TEXT    NOT NULL,     -- see services/pipeline.py REASONS
    detail       TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_intervention_utt ON interventions (utterance_id);

-- The three transcript levels plus the decision trace, per request.
CREATE TABLE utterances (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    asr_text           TEXT    NOT NULL,
    formatted_text     TEXT    NOT NULL,
    memory_aware_text  TEXT    NOT NULL,
    intervened         INTEGER NOT NULL DEFAULT 0,
    decision_trace     TEXT    NOT NULL DEFAULT '{}',   -- JSON
    latency_ms         REAL    NOT NULL DEFAULT 0.0,
    llm_calls          INTEGER NOT NULL DEFAULT 0,
    llm_mode           TEXT    NOT NULL DEFAULT 'mock',
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);
