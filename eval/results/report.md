# Kivi Phonetic Memory — Evaluation Report

- generated: `2026-09-05T15:18:08Z`
- llm mode: `mock`  ·  total LLM calls: **0**
- dataset: `eval/dataset/cases.yaml`  ·  cases: **34** (32 scored + 2 known-limitation)
- **scored: passed 32 / 32**  ·  failed: 0
- db file after full run (all 34 cases, one utterance each): 81,920 bytes

## Headline metrics

_Computed over the scored cases. Known-limitation cases are excluded here and listed in their own section so they cannot skew the numbers._

| metric | value | reading |
|---|---|---|
| intervention precision | **1.000** | of the rewrites Kivi made, how many were the right call |
| intervention recall | **1.000** | of the rewrites it should have made, how many it made |
| do-nothing accuracy | **1.000** | of the sentences it should have left alone, how many it did |
| latency p50 / p95 | 7.47 ms / 20.09 ms | mock LLM; add model latency for `--live` |
| LLM calls (whole suite) | 0 | mock mode issues none; `--live` issues one per utterance |

Outcome mix (scored): TP 16 · FP 0 · TN 14 · FN 0 · ambiguous handled 2 · ambiguous mishandled 0

## Useful interventions (16)

| case | input (formatted) | → memory-aware | reason | notes |
|---|---|---|---|---|
| `brief_example_multiterm` | Ask Aditya to review the Sarvam Kiwi service. | Ask Aaditya to review the Sarvam Kivi service. | `applied` |  |
| `person_spelling_promoted_after_two` | Sara owns the rollout. | Sarah owns the rollout. | `applied` |  |
| `product_casing_from_dictionary` | Ship the kivi build tonight. | Ship the Kivi build tonight. | `applied` |  |
| `jargon_two_token_alias` | Move the queue to Post Gres. | Move the queue to Postgres. | `applied` |  |
| `jargon_pytorch_from_corrections` | Profile the Pie Torch model. | Profile the PyTorch model. | `applied` |  |
| `brand_lowercase_to_canonical` | Servam shipped the release. | Sarvam shipped the release. | `applied` |  |
| `repeated_term_two_occurrences` | Restart kivi then redeploy kivi. | Restart Kivi then redeploy Kivi. | `applied` |  |
| `multiword_next_js` | The Next Js router changed. | The Next.js router changed. | `applied` |  |
| `multiword_type_script` | Rewrite it in Type Script. | Rewrite it in TypeScript. | `applied` |  |
| `context_resolves_ambiguity` | Remind Jon and then tell Jhon the plan. | Remind Jon and then tell Jon the plan. | `applied` |  |
| `one_rejection_is_not_enough` | Sara approved it. | Sarah approved it. | `applied` |  |
| `mixed_sentence_two_entries` | Tell Sara the kivi demo is ready. | Tell Sarah the Kivi demo is ready. | `applied` |  |
| `org_alias_servam` | I met the Sarwam founders. | I met the Sarvam founders. | `applied` |  |
| `redis_alias` | Cache it in Reddis. | Cache it in Redis. | `applied` |  |
| `alias_auto_learned_from_asr` | Adhitya joins at noon. | Aaditya joins at noon. | `applied` |  |
| `long_sentence_mixed_outcomes` | Ask Aditya to service the Sarvam Kiwi cluster. | Ask Aaditya to service the Sarvam Kivi cluster. | `applied` |  |

## Unnecessary or incorrect interventions (0)

_none_

## Correct restraint (did nothing, on purpose) (16)

| case | input (formatted) | → memory-aware | reason | notes |
|---|---|---|---|---|
| `empty_memory_passthrough` | Ask Aditya to review the Sarvam Kiwi service. | Ask Aditya to review the Sarvam Kiwi service. | `—` |  |
| `homophone_food_kiwi` | I ate a kiwi for breakfast. | I ate a kiwi for breakfast. | `food_context_guard` |  |
| `homophone_food_kiwi_salad` | The kiwi salad was fresh. | The kiwi salad was fresh. | `food_context_guard` |  |
| `common_word_service` | The service was slow today. | The service was slow today. | `common_word_guard` |  |
| `common_word_join` | Please join the standup. | Please join the standup. | `common_word_guard` |  |
| `common_word_mark` | Mark the ticket as done. | Mark the ticket as done. | `common_word_guard` |  |
| `weak_evidence_stays_candidate` | Loop in Nikhil please. | Loop in Nikhil please. | `not_active` |  |
| `suppressed_entry_not_applied` | Jane will present. | Jane will present. | `suppressed` |  |
| `already_canonical_noop` | Ask Aaditya to review it. | Ask Aaditya to review it. | `already_canonical` |  |
| `no_relevant_memory` | The weather is nice today. | The weather is nice today. | `—` |  |
| `deleted_entry_not_applied` | Convert it to Pie Torch. | Convert it to Pie Torch. | `—` |  |
| `proper_noun_collision_cologne` | We flew to Cologne last week. | We flew to Cologne last week. | `weak_surface_match` |  |
| `proper_noun_collision_terracotta` | The Terra cotta pots cracked. | The Terra cotta pots cracked. | `weak_surface_match` |  |
| `distinct_name_left_alone` | Neha will lead the sync. | Neha will lead the sync. | `weak_surface_match` |  |
| `ambiguous_two_people_no_context` | Ask Jhon to sign off. | Ask Jhon to sign off. | `ambiguous_conflict` |  |
| `ambiguous_near_duplicate_spellings` | Saara owns the doc. | Saara owns the doc. | `ambiguous_conflict` |  |

## Known limitations (2)

_Documented design boundaries of a word-level phonetic memory. Kept in the suite so they stay visible; excluded from the headline metrics._

### `morphology_plural_known_limitation` — diverges from the ideal
- known_limitation — "kiwis" is an inflected form; Kivi matches it phonetically to "Kivi" and rewrites, dropping the plural. A word-level phonetic memory has no morphology model.
- input:    `I bought two kiwis at the market.`
- ideal:    `I bought two kiwis at the market.`
- actual:   `I bought two Kivi at the market.`

### `food_guard_is_sentence_level_known_limitation` — diverges from the ideal
- known_limitation — the food-context guard is sentence-level, so an eating clause earlier in the sentence suppresses a legitimate later "Kivi". Disentangling the two clauses needs sentence understanding beyond word-level memory.
- input:    `I ate lunch then joined the kivi review.`
- ideal:    `I ate lunch then joined the Kivi review.`
- actual:   `I ate lunch then joined the kivi review.`

## Every case

| case | class | outcome | pass | latency | reason tags |
|---|---|---|:--:|---:|---|
| `brief_example_multiterm` | should_intervene | TP | ✅ | 22.29 ms | apply:applied, skip:already_canonical, apply:applied, skip:common_word_guard |
| `person_spelling_promoted_after_two` | should_intervene | TP | ✅ | 6.34 ms | apply:applied |
| `product_casing_from_dictionary` | should_intervene | TP | ✅ | 9.34 ms | apply:applied |
| `jargon_two_token_alias` | should_intervene | TP | ✅ | 11.91 ms | apply:applied |
| `jargon_pytorch_from_corrections` | should_intervene | TP | ✅ | 19.54 ms | apply:applied |
| `brand_lowercase_to_canonical` | should_intervene | TP | ✅ | 15.02 ms | apply:applied |
| `repeated_term_two_occurrences` | should_intervene | TP | ✅ | 19.37 ms | apply:applied, apply:applied |
| `multiword_next_js` | should_intervene | TP | ✅ | 19.12 ms | apply:applied |
| `multiword_type_script` | should_intervene | TP | ✅ | 12.56 ms | apply:applied |
| `context_resolves_ambiguity` | should_intervene | TP | ✅ | 21.38 ms | skip:already_canonical, apply:applied |
| `one_rejection_is_not_enough` | should_intervene | TP | ✅ | 14.62 ms | apply:applied |
| `mixed_sentence_two_entries` | should_intervene | TP | ✅ | 18.79 ms | apply:applied, apply:applied |
| `org_alias_servam` | should_intervene | TP | ✅ | 7.47 ms | apply:applied |
| `redis_alias` | should_intervene | TP | ✅ | 5.55 ms | apply:applied |
| `alias_auto_learned_from_asr` | should_intervene | TP | ✅ | 6.5 ms | apply:applied |
| `empty_memory_passthrough` | should_not_intervene | TN | ✅ | 1.2 ms | — |
| `homophone_food_kiwi` | should_not_intervene | TN | ✅ | 4.72 ms | skip:food_context_guard |
| `homophone_food_kiwi_salad` | should_not_intervene | TN | ✅ | 4.94 ms | skip:food_context_guard |
| `common_word_service` | should_not_intervene | TN | ✅ | 5.13 ms | skip:common_word_guard |
| `common_word_join` | should_not_intervene | TN | ✅ | 6.1 ms | skip:common_word_guard |
| `common_word_mark` | should_not_intervene | TN | ✅ | 5.99 ms | skip:common_word_guard |
| `weak_evidence_stays_candidate` | should_not_intervene | TN | ✅ | 5.55 ms | skip:not_active |
| `suppressed_entry_not_applied` | should_not_intervene | TN | ✅ | 5.75 ms | skip:suppressed |
| `already_canonical_noop` | should_not_intervene | TN | ✅ | 5.61 ms | skip:already_canonical |
| `no_relevant_memory` | should_not_intervene | TN | ✅ | 6.94 ms | — |
| `deleted_entry_not_applied` | should_not_intervene | TN | ✅ | 1.14 ms | — |
| `morphology_plural_known_limitation` | should_not_intervene | FP | ❌ | 8.65 ms | apply:applied |
| `food_guard_is_sentence_level_known_limitation` | should_intervene | FN | ❌ | 6.58 ms | skip:food_context_guard |
| `proper_noun_collision_cologne` | should_not_intervene | TN | ✅ | 5.56 ms | skip:weak_surface_match |
| `proper_noun_collision_terracotta` | should_not_intervene | TN | ✅ | 6.59 ms | skip:weak_surface_match |
| `distinct_name_left_alone` | should_not_intervene | TN | ✅ | 11.77 ms | skip:weak_surface_match |
| `long_sentence_mixed_outcomes` | should_intervene | TP | ✅ | 20.09 ms | apply:applied, skip:common_word_guard, skip:already_canonical, apply:applied |
| `ambiguous_two_people_no_context` | ambiguous | AMB_OK | ✅ | 15.22 ms | skip:ambiguous_conflict |
| `ambiguous_near_duplicate_spellings` | ambiguous | AMB_OK | ✅ | 7.84 ms | skip:ambiguous_conflict |
