# RUN.md &mdash; setup, run, evaluate, reset

## Primary review method: **local application (Python + embedded SQLite)**

One process, one SQLite file, a static HTML frontend. No network access is
required at any point &mdash; the ASR path is a deterministic echo provider and the
optional semantic layer uses a **vendored** embedding model
(`backend/kivi/models/`). No API key, no Docker.

Everything below is copy-paste from the repository root.

## 1. Requirements

- Python 3.11+ (tested on 3.13)
- Node is **not** required (the frontend is a single static HTML file served by the API)
- All core decision logic is stdlib-only. Packages are needed only for the HTTP
  layer and the optional semantic context layer.

## 2. Setup

```bash
cd D:/Sarvam_AI
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Git Bash:            source .venv/Scripts/activate
pip install -r requirements.txt
```

`requirements.txt` includes `model2vec` + `numpy` for the semantic context layer.
If you skip them (or `pip install` only `fastapi uvicorn[standard] python-multipart`),
the system still runs: it falls back to the shipped keyword/semantic-field lexicon
automatically (`config.json` -> `semantic_context.backend`). Everything except
`serve` also runs with no dependencies at all.

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
   (the user's learned ASR sound-substitutions). Also exposed at `GET /api/phonetic-profile`.
3. **Evaluation** &mdash; **Load results** shows the committed metrics + full report.
4. **Reset** &mdash; one click restores the seed (the reset/repeat workflow).

### One-shot from the CLI (no server)

```bash
python manage.py process "Open the kiwi service."
python manage.py process "Kivi is green and oval."
```

## 5. Semantic context layer (optional, on by default)

A word list can never enumerate every word that signals a context. The semantic
layer turns each utterance into a meaning vector and compares it to the
**confirmed** and **rejected** examples of each candidate memory, so contexts
generalise past the hand-listed keywords ("edible", "green and oval", "crimson",
"on the kitchen counter" are all recognised as fruit-talk with nothing added to
any list).

- Vectoriser: **`model2vec`** static embedding model, vendored at
  `backend/kivi/models/potion-base-8M` (~31 MB). Offline, deterministic, pure
  numpy (no torch), ~0.1 ms/encode.
- Fallback: if `model2vec` / the model file is unavailable, a shipped
  semantic-field lexicon (`backend/kivi/data/semantic_fields.json`) is used
  instead &mdash; zero dependencies.
- It only feeds the existing REPLACE / KEEP / DEFER engine (the negative /
  deliberate-KEEP side in this version). Processing stays read-only w.r.t. memory.
- All knobs: `config.json` -> `semantic_context`
  (`enabled`, `backend`, `model_path`, `neg_gate`, `neg_floor`). Set
  `"enabled": false` for the pre-semantic keyword-only behaviour.
- The decision trace records `s_ctx_semantic` and a plain-English `context_note`.

## 5b. Grammar layer for homophones (rule-based, always on)

Surface match can't tell `see` from `sea`, and neither the keyword lists nor a
small embedding model reliably can. The **grammatical slot** of the word can:

```
I see you            pronoun before  -> verb  -> "see"  (KEEP)
the sea is huge      determiner + "is" -> noun -> "sea"  (REPLACE)
```

`backend/kivi/grammar.py` (stdlib, deterministic) classifies the span's slot
from the function words around it. A memory whose **canonical and matched alias
are both ordinary English words** (`backend/kivi/data/common_words.json`) is
treated as a homophone pair: only grammar (or a genuinely strong keyword/semantic
context) may drive a REPLACE - surface match and correction history cannot. When
grammar is unclear the word is left exactly as written. Reason codes:
`homophone_grammar`, `homophone_unclear`; the trace carries a `homophone` block.

## 6. Evaluation

```bash
python manage.py eval
```

Resets the DB before every case, runs `evaluation/dataset/cases.jsonl` (40 cases:
useful interventions, deliberate non-interventions, 5 `personal_phonetics`, and
5 `semantic_context`, 6 `homophone`, 1 `memory_stability` cases), and writes:

- `evaluation/results/summary.json` &mdash; headline metrics, latency, model usage, by-category
- `evaluation/results/report.md` &mdash; human-readable report
- `evaluation/results/cases/<id>.json` &mdash; per-case input, expected/actual output,
  expected/actual decision, scores, reason, latency
- `evaluation/results/failures/<id>.json` &mdash; one file per failing case (none currently)

These files are committed so a reviewer sees the numbers without running anything.
The run is **deterministic** (echo ASR + rule-based formatter + fixed `config.json`
+ fixed embedding weights). After the run the DB is left clean and seeded.

## 7. Tests

```bash
python -m unittest discover -s tests -p "test_basic.py" -v
```

32 tests: phonetics, fuzzy bounds, the pipeline behaviours, the read-only-processing
invariant, the learning pipeline, personal phonetics, the semantic context layer
(unlisted-word generalisation, no suppression of real software context,
disabled-flag fallback, read-only), and the grammar/homophone layer (verb slot
left alone, noun slot restored with no keyword context, mixed sentence, module).

## 8. Configuration

All thresholds and weights live in `config.json`. Highlights:

| Key | Meaning |
|---|---|
| `thresholds.replace` / `.defer` | combined-score bands for REPLACE / DEFER |
| `thresholds.ctx_neg` | negative-context score that triggers a hard KEEP |
| `personal_phonetics.*` | accent-profile retrieval + disambiguation knobs |
| `semantic_context.enabled` | turn the semantic layer on/off |
| `semantic_context.backend` | `model2vec` (embedding model) or `lexicon` |
| `semantic_context.model_path` | path to the vendored static model |
| `semantic_context.neg_gate` / `.neg_floor` | how a negative semantic separation maps onto `s_ctx_neg` |

The grammar/homophone layer has no config knobs; its data is
`backend/kivi/data/common_words.json` (extend the `common` set and `pos` map to
cover more pairs).

Values are provisional; `evaluation/results/report.md` is where they are validated.

## 9. Audio / recording notes

- The **Record** button posts a `webm/opus` blob to `POST /api/process-audio`.
- Live/recorded audio needs a **real** ASR provider. The default `asr_provider` is
  `echo` (typed text only); set `"asr_provider": "whisper"` in `config.json` and
  install `faster-whisper` + `ffmpeg` for real transcription, or `"fixture"` for
  stored transcripts. With `echo`, `/api/process-audio` returns HTTP 409.
- The **evaluation harness always uses `echo`** for determinism.

## 10. Reset / repeat

```bash
python manage.py reset          # CLI
# or the "Reset to seed" button on the Reset tab
# or  POST /api/admin/reset
```

Idempotent, always recovers, and is what `eval` runs before each case.
