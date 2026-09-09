-- 0001_init: core schema for Kivi personal phonetic memory
-- Five concepts: memory / alias / observation / evidence, plus request + decision for the pipeline.

CREATE TABLE schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- The canonical personal entity and everything learned about how this person uses it.
CREATE TABLE memory (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_form       TEXT NOT NULL,
    normalized_canonical TEXT NOT NULL,
    entity_type          TEXT NOT NULL DEFAULT 'term',
    status               TEXT NOT NULL DEFAULT 'proposed',   -- proposed | active | contested | inactive
    confidence           REAL NOT NULL DEFAULT 0.0,
    positive_contexts    TEXT NOT NULL DEFAULT '{"keywords":[],"domains":[]}',
    negative_contexts    TEXT NOT NULL DEFAULT '{"keywords":[],"domains":[]}',
    source               TEXT NOT NULL DEFAULT 'user',       -- seed | user_taught | auto_learned
    notes                TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_memory_norm ON memory(normalized_canonical);
CREATE INDEX idx_memory_status ON memory(status);

-- One observed surface form (spelling / ASR mangling / abbreviation) that could mean the memory.
CREATE TABLE alias (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id         INTEGER NOT NULL REFERENCES memory(id) ON DELETE CASCADE,
    surface_form      TEXT NOT NULL,
    normalized_form   TEXT NOT NULL,
    phonetic_key      TEXT NOT NULL,
    origin            TEXT NOT NULL DEFAULT 'user',           -- seed | user | asr_observed
    observation_count INTEGER NOT NULL DEFAULT 0,
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_alias_mem_surface ON alias(memory_id, normalized_form);
CREATE INDEX idx_alias_norm ON alias(normalized_form);
CREATE INDEX idx_alias_phon ON alias(phonetic_key);

-- Immutable, append-only log of things the user actually did.
CREATE TABLE observation (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT NOT NULL,
    type             TEXT NOT NULL,   -- explicit_correction | confirmation | rejection | rejection_global | asr_pair | manual_teach | context_flag
    raw_asr_text     TEXT,
    formatted_text   TEXT,
    target_span      TEXT,
    chosen_form      TEXT,
    rejected_form    TEXT,
    context_snapshot TEXT,
    memory_id        INTEGER REFERENCES memory(id) ON DELETE SET NULL,
    decision_id      INTEGER
);
CREATE INDEX idx_obs_memory ON observation(memory_id);
CREATE INDEX idx_obs_decision ON observation(decision_id);

-- Weighted interpretation of observations. Confidence is a pure function of these rows.
CREATE TABLE evidence (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id      INTEGER NOT NULL REFERENCES memory(id) ON DELETE CASCADE,
    kind           TEXT NOT NULL,   -- strong_positive | weak_positive | negative_context | rejection | contradiction
    weight         REAL NOT NULL,
    context_key    TEXT,            -- domain this evidence is scoped to (nullable = global)
    observation_id INTEGER REFERENCES observation(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_evidence_memory ON evidence(memory_id, kind);

-- One row per /process call: the join point for the three transcript levels + cost/latency.
CREATE TABLE request (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                 TEXT NOT NULL,
    input_type         TEXT NOT NULL,   -- text | audio
    audio_ref          TEXT,
    asr_provider       TEXT,
    asr_text           TEXT,
    formatter_provider TEXT,
    formatted_text     TEXT,
    memory_aware_text  TEXT,
    latency_ms         REAL,
    model_calls        INTEGER DEFAULT 0,
    est_cost_usd       REAL DEFAULT 0.0
);

-- Full explainability record: one row per span that had at least one candidate.
CREATE TABLE decision (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id         INTEGER REFERENCES request(id) ON DELETE CASCADE,
    span_text          TEXT NOT NULL,
    span_start         INTEGER,
    span_end           INTEGER,
    asr_original       TEXT,
    candidate_memory_id INTEGER REFERENCES memory(id) ON DELETE SET NULL,
    match_method       TEXT,
    s_surf             REAL,
    s_ctx_pos          REAL,
    s_ctx_neg          REAL,
    s_ctx              REAL,
    mem_confidence     REAL,
    combined_score     REAL,
    ambiguity_flag     INTEGER DEFAULT 0,
    contradiction_flag INTEGER DEFAULT 0,
    action             TEXT NOT NULL,   -- REPLACE | KEEP | DEFER
    reason_code        TEXT,
    reason_text        TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX idx_decision_request ON decision(request_id);
