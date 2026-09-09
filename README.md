# Kivi · Personal Phonetic Memory

Word-level memory that moves a transcript from **formatted** to **memory-aware** —
so Kivi writes the words *this particular person* uses, the way they use them.

```
ASR         ask aditya to review the sarvam kiwi service
Formatted   Ask Aditya to review the Sarvam Kiwi service.
Memory-aware Ask Aaditya to review the Sarvam Kivi service.
```

`Aditya → Aaditya` is a preferred spelling ASR can't know. `Kiwi → Kivi` is a product
name a model has no reason to prefer. Kivi learns both from ordinary corrections and
applies them next time — while leaving the fruit alone in *"I ate a kiwi today."*

Kivi's dictionary is **not** a replacement list. A phonetic/fuzzy match only **nominates a
candidate**; a deterministic, explainable engine then decides **REPLACE / KEEP / DEFER**,
and records the scores + evidence + a plain-English reason for every word.

**Run it:** [`RUN.md`](RUN.md) — `python manage.py {reset|serve|eval|process}`.
Committed evaluation: [`evaluation/results/report.md`](evaluation/results/report.md).

---

## Pipeline

```
audio/text
 → ASR              level 1: raw transcript                       (echo provider; Whisper optional)
 → formatter        level 2: generic punctuation / casing         (rule-based)
 → span builder     align formatted tokens ↔ ASR tokens
 → retrieval        exact / normalized / fuzzy / phonetic / personal   → candidates only
 → context + evidence   positive/negative context, confidence, contradiction
 → decision engine  multiplicative score + hard gates             → REPLACE / KEEP / DEFER
 → rewriter         level 3: memory-aware transcript
 → decision trace   why every word changed, or was deliberately left alone
```

Processing is **read-only** w.r.t. memory. Only user observations (`/api/observe`) mutate it.
No LLM in the core path — `model_calls` and `est_cost_usd` are `0` by design.

## Core ideas

| Idea | Where |
|---|---|
| A phonetic hit is a **nomination**, not a verdict | `backend/kivi/memory/retrieval.py` |
| **Confidence** (is this real?) and **applicability** (does it apply here?) are separate axes | `memory/confidence.py` + `context.py` |
| **Context-scoped negative evidence** — rejecting *"I ate a kiwi"* never weakens the `Kivi` memory | `memory/learning.py` (`negative_context`, excluded from confidence) |
| **DEFER** is a real outcome — ambiguity, weak/`proposed` memory, contradiction | `decision.py` |
| **Deliberate non-intervention** is first-class, tested, and measured | eval metric `non_intervention_accuracy`, `over_intervention_count` |
| Thresholds are named constants, treated as hypotheses validated by eval | `config.json`, `evaluation/results/report.md` |

## Personal (accent-adaptive) phonetics

A generic phonetic key encodes how English sounds *in general* — identical for everyone.
But one speaker + mic + ASR model mangles the same sounds the same way, repeatedly.

Each correction is aligned (`misheard ↔ chosen`) into small position-tagged substitution
rules — `w→v (medial)`, `l→r (onset)`, `∅→n (coda)` — that accumulate in an inspectable
`sound_pattern` table (the user's **accent profile**) and feed retrieval two ways:

1. **Candidate creation** — apply the profile to an unmatched span; if the result lands on
   a known memory, nominate it (`match_method = personal`). Catches `l`/`r`, `n`/`l`,
   dropped-coda confusions that share no generic key and fall below the fuzzy floor.
2. **Disambiguation prior** — a memory this user's ASR has demonstrably mangled before
   gets a small, capped boost that can break a near-tie (`ask civi` → `Kivi`, not `Sivi`).

The boost is applied **after** the hard gates, so it can never override a KEEP or
auto-apply a not-yet-active memory. The profile is written only by the learning path;
processing never grows it (asserted by the eval idempotency check). Config:
`config.json` → `personal_phonetics`. Module: `memory/phonetic_profile.py`.

## First-recall of an explicit correction

An **exact match to a stored alias, on an active memory the user has corrected before, in
neutral or positive context** skips the "positive context not warmed up yet" gate — so a
single explicit correction takes effect on the *next* occurrence, even in a sentence with
different surrounding words. The negative-context KEEP still wins: after teaching
`lusia → Lucia`, *"ask lusia to review the PR"* → **Lucia**, but *"the kiwi was ripe and
sweet"* still → **kiwi** (context leans away, `s_ctx < 0`). `decision.py`, `gate_forced`.

## Flagship behaviour

| Input | Memory-aware output | Why |
|---|---|---|
| `Open the kiwi service.` | `Open the **Kivi** service.` | active memory + software context |
| `I ate a kiwi today.` | *unchanged* | memory matches, but food is a do-not-apply context |
| `ask civi` | *DEFER* | `civi` fits both `Kivi` and colleague `Sivi` — too close to choose |
| `we should ship devy this sprint` | *DEFER* | `Devi` is only `proposed` — never auto-replaces |
| `deploy the Zephyr module` | *KEEP* | no memory; none is hallucinated |
| `tell lehan about the sync` *(after `lehaan`/`lehin` → `Rehan`)* | `Tell **Rehan** about the sync.` | learned accent rule `l→r (onset)` nominates what generic phonetics + fuzzy both miss |
| `ask civi` *(after 4× correcting `Kivi` mishearings)* | `Ask **Kivi**.` | history breaks the tie the bare `ask civi` above still DEFERs |

## Frontend

`frontend/index.html` + `frontend/styles.css`, served at `/`. Implements a design
imported from **claude.ai/design** (design-system tokens inlined verbatim). Three tabs —
**Transcribe** (memory-aware line only; click any word to correct it → writes to
`/api/observe` and re-runs), **Memory** (overview, accent profile, term table with
evidence), **Evaluation** (committed metrics + report).

## Stack

Python 3.11+, **stdlib only** for all core logic. FastAPI + uvicorn for the HTTP layer.
**SQLite** single file (`database/kivi.db`), plain numbered SQL migrations. Vanilla-JS SPA.

## Layout

```
manage.py                   migrate / seed / reset / serve / eval / process
config.json                 all thresholds & weights (validated by eval)
backend/kivi/               core: normalization, phonetics, retrieval, context, decision,
                            rewrite, explain, pipeline, memory/*, asr/*, formatter/*, db/*
  memory/phonetic_profile.py  accent-adaptive phonetics
backend/api/main.py         FastAPI endpoints (incl. GET /api/phonetic-profile)
database/migrations/        0001_init.sql, 0002_personal_phonetics.sql
database/seed/seed.json     5 seed memories + 1 seed accent rule
evaluation/dataset/         cases.jsonl (28: interventions, non-interventions, 5 personal)
evaluation/run.py           harness
evaluation/results/         COMMITTED: summary.json, report.md, cases/*, failures/*
frontend/                   index.html + styles.css
tests/test_basic.py         unittest suite
```

## Results (`evaluation/results/summary.json`)

- **28 / 28** cases pass · action accuracy 100% · exact output match 100%
- intervention precision / recall / F1 = **100%**
- **non-intervention accuracy 100%**, over-intervention **0**
- memory-stability **6/6** · idempotency **1/1** · personal-phonetics **5/5**
- latency p50 ≈ 1 ms, p95 ≈ 2 ms · model calls 0 · cost $0

The dataset is small and co-designed with the system — its value is the **methodology and
harness**, which records per-case scores and writes `failures/<id>.json` for any miss.

## Limitations

- **Food-context guard is sentence-level** — an eating clause anywhere suppresses a later
  legitimate product mention. Needs clause-level understanding beyond a word-level memory.
- **No morphology** — *"kiwis"* matches *"Kivi"* and the plural is dropped.
- English-centric phonetics; single-user; small hand-curated context word lists.

## AI use

Built with **Claude Code** as a pair-programmer against a design brief: it wrote the bulk
of the code, the eval dataset, and this document, and iterated the phonetic scoring and
decision guards against the test suite. Every design decision — the evidence model, the
confidence/applicability split, the closed reason vocabulary, gate ordering, the
first-recall rule, the acknowledged limitations — was reviewed and directed by me.
Runtime: **no AI** in the core path (deterministic phonetics / edit distance only). No
private corpus or pretrained phonetic model.
