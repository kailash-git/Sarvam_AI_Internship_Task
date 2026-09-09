<<<<<<< HEAD
# RUN.md &mdash; setup, run, evaluate, reset

## 1. Requirements

- Python 3.11+ (tested on 3.13)
- Node is **not** required (the frontend is a single static HTML file served by the API)
- All core logic is stdlib-only. Only the HTTP layer needs packages.

## 2. Setup

```bash
cd D:/Sarvam_AI
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Git Bash:            source .venv/Scripts/activate
pip install -r requirements.txt
```

(You can also run everything except `serve` with no dependencies at all.)

## 3. Initialise the database

```bash
python manage.py reset
```

This deletes `database/kivi.db`, re-applies `database/migrations/*.sql`, and loads
`database/seed/seed.json`. Expected output (counts): `memory=5, alias=12, observation=18,
evidence=18, request=0, decision=0, sound_pattern=1` and seed memories:

```
Kivi=0.8405(active)  Sarvam=0.7448(active)  MCP=0.7122(active)
Sivi=0.7122(active)  Devi=0.3787(proposed)
```

`sound_pattern=1` is the one seeded **accent rule** (`w->v (medial)`, representing prior
onboarding). The accent profile is otherwise learned from corrections at runtime.

`migrate` and `seed` are also available separately.

## 4. Run the app

```bash
python manage.py serve
```

Open <http://127.0.0.1:8000> &mdash; four tabs:

1. **Try it** &mdash; type an utterance (or click **Record** to capture your microphone),
   press **Process**, see the three transcript levels and the decision trace. Use
   **confirm / reject** on any trace row to teach the memory, then watch it re-process.
2. **Memory** &mdash; browse memories; click a row for aliases, evidence, contexts,
   observations; teach a new memory. The top panel shows the **accent profile**
   (the user's learned ASR sound-substitutions); it grows as you confirm/reject
   mishearings. Also exposed at `GET /api/phonetic-profile`.
3. **Evaluation** &mdash; **Load results** shows the committed metrics + full report.
4. **Reset** &mdash; one click restores the seed (the reset/repeat workflow).

### One-shot from the CLI (no server)

```bash
python manage.py process "Open the kiwi service."
python manage.py process "I ate a kiwi today."
```

## 5. Evaluation

```bash
python manage.py eval
```

Resets the DB before every case, runs `evaluation/dataset/cases.jsonl` (28 cases:
useful interventions, deliberate non-interventions, and 5 `personal_phonetics` cases),
and writes:

- `evaluation/results/summary.json` &mdash; headline metrics, latency, model usage,
  by-category, and a `personal_phonetics` block (what each accent case demonstrates)
- `evaluation/results/report.md` &mdash; human-readable report incl. a
  **Personal (accent-adaptive) phonetics** section and a **Failures** section
- `evaluation/results/cases/<id>.json` &mdash; per-case: input, expected/actual output,
  expected/actual decision, scores, reason, latency
- `evaluation/results/failures/<id>.json` &mdash; one file per failing case (none currently)

These files are committed so a reviewer sees the numbers without running anything.
The run is **deterministic** (echo ASR + rule-based formatter + fixed `config.json`) &mdash;
re-running produces identical `summary.json`. After the run the DB is left clean and seeded.

## 6. Tests

```bash
python -m unittest discover -s tests -v
```

Covers phonetics, fuzzy bounds, the five pipeline behaviours (software REPLACE, fruit KEEP,
ambiguity DEFER, weak-memory no-auto-replace, unknown-word KEEP), the read-only-processing
invariant, the learning pipeline (scoped rejection does not touch global confidence;
scoped rejection blocks one context only; correction creates a memory that then replaces),
and **personal phonetics** (rule derivation is position-tagged and directional; a learned
accent rule nominates a never-seen mishearing; correction history lifts a borderline match;
the accent profile never overrides a deliberate KEEP and does not grow during processing).

## 7. Configuration

All thresholds and weights live in `config.json`:

| Key | Meaning |
|---|---|
| `thresholds.replace` / `.defer` | combined-score bands for REPLACE / DEFER |
| `thresholds.ctx_neg` | negative-context score that triggers a hard KEEP (deliberate non-intervention) |
| `thresholds.ctx_pos` / `.ctx_low` | context-gate shaping |
| `thresholds.phonetic_fuzzy_floor` | a phonetic-key match also needs this much fuzzy similarity to become a candidate |
| `thresholds.ambiguity_margin` | max combined-score gap between two memories to call it ambiguous -> DEFER |
| `confidence.*` | logistic parameters + `authoritative_floor` (an explicit user correction is confident by definition) |
| `personal_phonetics.min_observations` | how many times a learned accent rule must be seen before it fires in retrieval |
| `personal_phonetics.match_floor` / `.match_score_cap` | similarity floor for an accent-nominated candidate, and the ceiling on its surface score (kept below an exact hit) |
| `personal_phonetics.combined_boost` | max multiplicative lift on the combined score from "this user's ASR has mangled this memory before" |
| `personal_phonetics.tiebreak_min_count` | correction-count gap at which history breaks an otherwise-ambiguous match |

Values are provisional; `evaluation/results/report.md` is where they are validated.

## 8. Audio / recording notes

- The **Record** button uses the browser `MediaRecorder` API and posts a `webm/opus` blob
  to `POST /api/process-audio`.
- Live/recorded audio needs a **real** ASR provider. The default `asr_provider` is `echo`
  (typed text only); set `"asr_provider": "whisper"` in `config.json` and install
  `faster-whisper` + `ffmpeg` for real transcription, or `"fixture"` for stored transcripts.
  With `echo`, `/api/process-audio` returns HTTP 409 with an explanatory message.
- The **evaluation harness always uses `echo`** for determinism; live recordings are never
  part of the eval set.

## 9. Reset / repeat

```bash
python manage.py reset          # CLI
# or the "Reset to seed" button on the Reset tab
# or  POST /api/admin/reset
```

Idempotent, always recovers, and is what `eval` runs before each case.
=======
# RUN.md

## Primary review method: **local application, Python + embedded SQLite**

No network, no API key, no Docker required. The LLM step runs in a deterministic
mock by default, so the demo and the evaluation are fully reproducible offline.
A Docker path and a live-LLM path are documented at the end as alternatives.

Everything below is copy-paste from the repository root.

---

### 1. Required runtimes and versions

| requirement | version | notes |
|---|---|---|
| Python | **3.11 – 3.13** (developed on 3.13) | only the standard library + the pinned packages below |
| pip | any recent | |
| OS | Linux, macOS, or Windows | paths in commands use forward slashes; on Windows use the venv path shown |

No database server, no Node, no build step.

### 2. Required environment variables

**None are required.** Defaults are baked in. Optional overrides (see
`.env.example`):

| variable | default | meaning |
|---|---|---|
| `KIVI_LLM_MODE` | `mock` | `mock` = deterministic offline; `live` = call Anthropic |
| `ANTHROPIC_API_KEY` | *(empty)* | required **only** if `KIVI_LLM_MODE=live` |
| `KIVI_LLM_MODEL` | `claude-sonnet-5` | model id for `live` mode |
| `KIVI_DB_PATH` | `./kivi.db` | SQLite file for the app (the eval uses its own file) |
| `KIVI_APPLY_THRESHOLD` | `0.72` | score at/above which a memory entry is applied |
| `KIVI_PROMOTE_AFTER` | `2` | corroborating corrections to promote candidate → active |
| `KIVI_SUPPRESS_AFTER` | `2` | rejections to suppress an entry |

### 3. Install dependencies

```bash
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
#   .venv\Scripts\Activate.ps1
# Windows (Git Bash):
#   source .venv/Scripts/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create, migrate, and seed the database

```bash
python -m app.db.migrate      # creates ./kivi.db and applies migrations
python -m app.db.seed         # loads reproducible seed data (prints a stats summary)
```

`python -m app.db.migrate --status` shows applied vs pending migrations.

### 5. Start every required process

Exactly one process:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

(The server also runs migrations on startup, so step 4's migrate is optional if
you start here; the seed is not automatic — run it, or click **Reset & reseed**
in the UI.)

### 6. Interface to open

Open **http://127.0.0.1:8000/** in a browser.

A scriptable command-line interface over the same core is also available — see
"CLI" below. RUN.md's declared primary interface is the browser UI.

### 7. Primary interactions to try

In the web UI, top to bottom:

1. **Section 1 — Speak again.** The ASR + formatted boxes are pre-filled with the
   brief's example. Click **Run**. You should see
   `Ask Aaditya to review the Sarvam Kivi service.` with a decision table:
   `Aditya→Aaditya` applied, `Kiwi→Kivi` applied, `Sarvam` already-canonical,
   `service` skipped by the common-word guard.
2. Click the **homophone (do nothing)** example, then **Run**. The text is left
   as `I ate a kiwi for breakfast.` — reason `food_context_guard`.
3. Click **jargon**, then **Run** → `... to PyTorch and Postgres.`
4. Click **ambiguous**, then **Run** → unchanged, reason `ambiguous_conflict`
   (both `Jon` and `John` are in memory).
5. **Section 2 — Teach Kivi.** On the *correction* tab, change the corrected text
   and click **Learn from correction**; on the *dictionary* tab add a word. Watch
   the stats row and the memory table update.
6. **Section 3 — Memory state.** Filter by `candidate` / `suppressed`; use
   *activate* / *suppress* / *delete* on a row.
7. **Section 4 — Recent utterances.** Expand any row to see the full JSON
   decision trace that was persisted.
8. **Reset & reseed** (top right) returns to the initial state.

### 8. Run the evaluation

```bash
python -m eval.run
```

Runs all cases in `eval/dataset/cases.yaml`, each in an isolated database
(`eval/_eval.db`, created and destroyed by the run). Deterministic; needs no key.

Options: `python -m eval.run --case brief_example_multiterm` (one case, verbose
JSON), `python -m eval.run --live` (use the real Anthropic API).

### 9. Where evaluation results are written

| file | contents |
|---|---|
| `eval/results/results.json` | every case: inputs, expected, actual, memory state, decisions, outcome, latency |
| `eval/results/report.md` | summary, headline metrics, the useful-vs-unnecessary intervention ledgers, known-limitation section, per-case table, failure detail |

Both are committed in this repo (generated with `KIVI_LLM_MODE=mock`) and are
overwritten in place on each run.

### 10. Reset procedure

- **From the UI:** click **Reset & reseed**.
- **From the CLI:** `python -m cli.kivi reset` (add `--no-seed` for an empty memory).
- **From the API:** `curl -X POST localhost:8000/api/reset -H 'content-type: application/json' -d '{"seed": true}'`
- **Hard reset:** delete the SQLite file — `rm -f kivi.db kivi.db-*` — then repeat step 4.

The evaluation always resets its own database per case; nothing to do manually.

---

## CLI (same core, no server)

```bash
python -m cli.kivi --help
python -m cli.kivi reset
python -m cli.kivi walkthrough        # scripted end-to-end narrative
python -m cli.kivi memory
python -m cli.kivi teach-word --canonical Kivi --category product --alias kiwi
python -m cli.kivi teach-correction --formatted "Tell Aditya." --corrected "Tell Aaditya." --category person
python -m cli.kivi format --asr "ask aditya about kivi" --formatted "Ask Aditya about Kiwi."
```

## Tests

```bash
pip install -r requirements.txt      # pytest is included
python -m pytest -q
```

## Alternative: Docker

```bash
docker compose up --build            # serves the same app on http://127.0.0.1:8000/
docker compose run --rm kivi python -m eval.run
```

The database is a named volume; `docker compose down -v` resets it.

## Alternative: live LLM

```bash
cp .env.example .env
# set KIVI_LLM_MODE=live and ANTHROPIC_API_KEY=... in .env
python -m uvicorn app.main:app --port 8000      # UI now uses the real model
python -m eval.run --live                       # eval against the real model
```

In `live` mode the model is asked to apply the same glossary, but the pipeline
only accepts edits that match an intervention it independently decided on, so the
output stays exactly as inspectable as in `mock` mode.
>>>>>>> 6d3bcdf4a6716ab829c395c210736b0c12063223
