# Kivi Personal Phonetic Memory - Evaluation Report

_Deterministic run: echo ASR + rule-based formatter + fixed `config.json`._

## Headline metrics

| Metric | Value |
|---|---|
| Cases | 28 |
| Passed | 28 (100.0%) |
| Action accuracy | 100.0% |
| Exact output match | 100.0% |
| **Intervention precision** | **100.0%** |
| Intervention recall | 100.0% |
| Intervention F1 | 100.0% |
| **Non-intervention accuracy** | **100.0%** |
| Defer accuracy | 100.0% |
| Over-intervention count | 0 |
| Memory-stability pass | 6/6 |
| Idempotency pass | 1/1 |

## Latency / model usage / cost

| Metric | Value |
|---|---|
| Latency p50 | 3.145 ms |
| Latency p95 | 14.52 ms |
| Latency max | 14.56 ms |
| Total model calls | 0 |
| Total est. cost | $0.0 |

> 0 by design: echo ASR + rule-based formatter, no LLM in the core path

## By category

| Category | Passed / Total |
|---|---|
| acronym_false_friend | 1 / 1 |
| ambiguous_candidate | 1 / 1 |
| conflicting_memories | 1 / 1 |
| contextual_contradiction | 3 / 3 |
| entity_type_acronym | 1 / 1 |
| entity_type_company | 1 / 1 |
| entity_type_person | 1 / 1 |
| exact_match | 1 / 1 |
| explicit_correction | 1 / 1 |
| fuzzy_match | 1 / 1 |
| idempotency | 1 / 1 |
| multi_entity | 1 / 1 |
| new_word | 1 / 1 |
| normalized_match | 1 / 1 |
| personal_phonetics | 5 / 5 |
| phonetic_match | 1 / 1 |
| repeated_observation | 1 / 1 |
| strong_memory | 1 / 1 |
| user_confirmation | 1 / 1 |
| user_rejection | 2 / 2 |
| weak_memory | 1 / 1 |

## Personal (accent-adaptive) phonetics

- cases: **5 / 5** passed
- reason-string assertions: **3/3**
- Accent profile starts empty; every personal_phonetics case learns its rules from `setup` corrections before the pipeline runs. It never overrides a deliberate KEEP or a not-yet-active memory.

| What it demonstrates | Cases |
|---|---|
| nomination (accent rule creates the candidate) | personal-learn-01 |
| prior (history lifts a borderline match) | personal-prior-01, personal-tiebreak-01 |
| safety (accent signal must not override KEEP) | personal-safety-01, personal-noop-01 |

## Per-case results

| ID | Category | Expected | Actual | Output OK | Pass | Reason |
|---|---|---|---|---|---|---|
| exact-01 | exact_match | REPLACE | REPLACE | yes | PASS | Replaced 'kivi' with 'Kivi': exact match (surface 1.00) to an active memory (confidence 0. |
| normalized-01 | normalized_match | REPLACE | REPLACE | yes | PASS | Replaced 'kiwi' with 'Kivi': exact match (surface 1.00) to an active memory (confidence 0. |
| fuzzy-01 | fuzzy_match | REPLACE | REPLACE | yes | PASS | Replaced 'kivee' with 'Kivi': phonetic match (surface 0.85) to an active memory (confidenc |
| phonetic-01 | phonetic_match | REPLACE | REPLACE | yes | PASS | Replaced 'kibi' with 'Kivi': phonetic match (surface 0.85) to an active memory (confidence |
| strong-01 | strong_memory | REPLACE | REPLACE | yes | PASS | Replaced 'kiwi' with 'Kivi': exact match (surface 1.00) to an active memory (confidence 0. |
| noninterv-01 | contextual_contradiction | KEEP | KEEP | yes | PASS | Kept 'kiwi' unchanged. Memory 'Kivi' matches (exact, 1.00), but the surrounding words matc |
| noninterv-02 | contextual_contradiction | KEEP | KEEP | yes | PASS | Kept 'kiwi' unchanged. Memory 'Kivi' matches (exact, 1.00), but the surrounding words matc |
| weak-01 | weak_memory | DEFER | DEFER | yes | PASS | Suggested 'Devi' for 'devy' but memory is 'proposed' (confidence 0.38); needs your confirm |
| ambiguous-01 | ambiguous_candidate | DEFER | DEFER | yes | PASS | Deferred on 'civi'. It matches 'Kivi' (0.42) and 'Sivi' (0.36); scores are too close to ch |
| newword-01 | new_word | KEEP | KEEP | yes | PASS | no candidate matched this span |
| acronym-01 | entity_type_acronym | REPLACE | REPLACE | yes | PASS | Replaced 'mcb' with 'MCP': exact match (surface 1.00) to an active memory (confidence 0.71 |
| acronym-02 | acronym_false_friend | KEEP | KEEP | yes | PASS | no candidate matched this span |
| company-01 | entity_type_company | REPLACE | REPLACE | yes | PASS | Replaced 'sarwam' with 'Sarvam': exact match (surface 1.00) to an active memory (confidenc |
| person-01 | entity_type_person | REPLACE | REPLACE | yes | PASS | Replaced 'sibi' with 'Sivi': exact match (surface 1.00) to an active memory (confidence 0. |
| correction-01 | explicit_correction | REPLACE | REPLACE | yes | PASS | Replaced 'nimbers' with 'Nimbus': exact match (surface 1.00) to an active memory (confiden |
| repeated-01 | repeated_observation | DEFER | DEFER | yes | PASS | Suggested 'Lumen' for 'lumen' but memory is 'proposed' (confidence 0.38); needs your confi |
| rejection-01a | user_rejection | KEEP | KEEP | yes | PASS | Kept 'kiwi' unchanged. Memory 'Kivi' matches (exact, 1.00), but the surrounding words matc |
| rejection-01b | user_rejection | REPLACE | REPLACE | yes | PASS | Replaced 'kiwi' with 'Kivi': exact match (surface 1.00) to an active memory (confidence 0. |
| conflict-01 | conflicting_memories | DEFER | DEFER | yes | PASS | Deferred on 'kaya'. It matches 'Kayo' (0.77) and 'Kaira' (0.77); scores are too close to c |
| idempotency-01 | idempotency | REPLACE | REPLACE | yes | PASS | Replaced 'kiwi' with 'Kivi': exact match (surface 1.00) to an active memory (confidence 0. |
| multi-01 | multi_entity | DEFER | DEFER | yes | PASS | Deferred on 'sibi'. 'Sivi' is plausible (combined 0.42) but below the replace threshold (0 |
| noninterv-03 | contextual_contradiction | KEEP | KEEP | yes | PASS | no candidate matched this span |
| confirm-01 | user_confirmation | REPLACE | REPLACE | yes | PASS | Replaced 'hallo' with 'Halo': exact match (surface 1.00) to an active memory (confidence 0 |
| personal-learn-01 | personal_phonetics | REPLACE | REPLACE | yes | PASS | Replaced 'lehan' with 'Rehan': personal match (surface 0.88) to an active memory (confiden |
| personal-prior-01 | personal_phonetics | REPLACE | REPLACE | yes | PASS | Replaced 'sibi' with 'Sivi': exact match (surface 1.00) to an active memory (confidence 0. |
| personal-tiebreak-01 | personal_phonetics | REPLACE | REPLACE | yes | PASS | Replaced 'civi' with 'Kivi': phonetic match (surface 0.85) to an active memory (confidence |
| personal-safety-01 | personal_phonetics | KEEP | KEEP | yes | PASS | Kept 'kiwi'. 'Kivi' matched but the combined score (0.25) is below the defer threshold (0. |
| personal-noop-01 | personal_phonetics | KEEP | KEEP | yes | PASS | no candidate matched this span |

## Failures

_None - all cases passed._

_Generated 2026-09-08 08:30:38 local._