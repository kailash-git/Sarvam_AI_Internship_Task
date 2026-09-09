"""Reproducible evaluation for Kivi's phonetic memory.

What this proves
----------------
The product claim is: *Kivi rewrites a formatted transcript to match the words a
user has taught it, and stays out of the way otherwise.* So every case declares
a class:

    should_intervene       memory must change the text (useful learning)
    should_not_intervene   memory must leave the text alone (correct restraint)
    ambiguous              evidence is genuinely unclear; the safe move is to
                           do nothing, and say why

Each case runs in a fully isolated database: reset -> apply the case's seed
observations -> run the pipeline once. For every case we persist the inputs, the
expected result, the actual result, the resulting memory state, and the
reason(s) the system gave. Results are written to:

    eval/results/results.json     every case, machine-readable
    eval/results/report.md        summary, metrics, and the two intervention
                                  ledgers (useful vs unnecessary/incorrect)

Usage
-----
    python -m eval.run                 # mock LLM, deterministic, offline
    python -m eval.run --live          # use the real Anthropic API (needs key)
    python -m eval.run --case brief_example_multiterm   # one case, verbose
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = Path(__file__).resolve().parent / "dataset" / "cases.yaml"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
EVAL_DB = str(REPO_ROOT / "eval" / "_eval.db")


def _prepare_env(live: bool) -> None:
    os.environ["KIVI_DB_PATH"] = EVAL_DB
    os.environ["KIVI_LLM_MODE"] = "live" if live else "mock"
    for f in (EVAL_DB, EVAL_DB + "-wal", EVAL_DB + "-shm", EVAL_DB + "-journal"):
        Path(f).unlink(missing_ok=True)


def _apply_seed(seed: dict) -> None:
    from app.services import learning, repo

    for corr in seed.get("corrections", []):
        learning.learn_from_correction(
            asr_text=corr.get("asr", ""),
            formatted_text=corr["formatted"],
            corrected_text=corr["corrected"],
            category=corr.get("category", "other"),
            note=corr.get("note", ""),
        )
    for word in seed.get("dictionary", []):
        learning.learn_from_dictionary(
            canonical=word["canonical"],
            category=word.get("category", "other"),
            aliases=word.get("aliases", []),
            note=word.get("note", ""),
        )
    for spec in seed.get("reject", []):
        entry = repo.find_entry(spec["canonical"], spec.get("category", "other"))
        if not entry:
            raise ValueError(f"reject target not found: {spec}")
        for _ in range(int(spec.get("times", 1))):
            learning.learn_from_rejection(entry_id=entry["id"], note="eval reject")
    for spec in seed.get("delete", []):
        entry = repo.find_entry(spec["canonical"], spec.get("category", "other"))
        if entry:
            repo.delete_entry(entry["id"])
    for spec in seed.get("accept", []):
        entry = repo.find_entry(spec["canonical"], spec.get("category", "other"))
        if entry:
            for _ in range(int(spec.get("times", 1))):
                learning.learn_from_acceptance(entry_id=entry["id"])


def _classify(case: dict, actual: dict) -> str:
    """One of: TP, FP, TN, FN, AMB_OK, AMB_BAD."""
    clazz = case["clazz"]
    text_ok = actual["memory_aware_text"] == case["expect"]["memory_aware"]
    want_intervene = bool(case["expect"].get("intervened", clazz == "should_intervene"))
    did_intervene = actual["intervened"]

    if clazz == "should_intervene":
        return "TP" if (text_ok and did_intervene) else "FN"
    if clazz == "should_not_intervene":
        if did_intervene or not text_ok:
            return "FP"
        return "TN"
    # ambiguous
    if did_intervene == want_intervene and text_ok:
        return "AMB_OK"
    return "AMB_BAD"


def _reason_ok(case: dict, actual: dict) -> bool:
    want = case["expect"].get("reason")
    if not want:
        return True
    tags = {d["reason_tag"] for d in actual["decisions"]}
    return want in tags


def run_case(case: dict) -> dict:
    from app.services import admin, repo
    from app.services.pipeline import process

    admin.reset(seed=False)
    _apply_seed(case.get("seed", {}))
    memory_before = repo.list_entries()

    t0 = time.perf_counter()
    result = process(case["input"]["asr"], case["input"]["formatted"], persist=True)
    wall_ms = round((time.perf_counter() - t0) * 1000, 2)

    actual = {
        "memory_aware_text": result.memory_aware_text,
        "intervened": result.intervened,
        "decisions": [
            {
                "action": d.action, "span_text": d.span_text, "canonical": d.canonical,
                "reason_tag": d.reason_tag, "detail": d.detail,
                "phonetic_score": d.phonetic_score, "combined_score": d.combined_score,
                "threshold": d.threshold,
            }
            for d in result.decisions
        ],
        "llm_calls": result.trace["llm_calls"],
        "latency_ms": result.trace["latency_ms"],
    }
    outcome = _classify(case, actual)
    reason_ok = _reason_ok(case, actual)
    passed = outcome in ("TP", "TN", "AMB_OK") and reason_ok

    return {
        "id": case["id"],
        "description": case["description"],
        "clazz": case["clazz"],
        "known_limitation": bool(case.get("known_limitation", False)),
        "inputs": case["input"],
        "expected": case["expect"],
        "actual": actual,
        "memory_state": [
            {k: e[k] for k in ("id", "canonical", "category", "status", "confidence")}
            | {"aliases": [a["surface_form"] for a in e["aliases"]]}
            for e in memory_before
        ],
        "outcome": outcome,
        "reason_ok": reason_ok,
        "passed": passed,
        "wall_ms": wall_ms,
    }


def _metrics(all_cases: list[dict]) -> dict:
    # Headline metrics are computed over scored cases only. known_limitation
    # cases are documented design boundaries, tracked separately so they cannot
    # quietly inflate or deflate the numbers.
    cases = [c for c in all_cases if not c["known_limitation"]]
    counts = {k: 0 for k in ("TP", "FP", "TN", "FN", "AMB_OK", "AMB_BAD")}
    for c in cases:
        counts[c["outcome"]] += 1
    tp, fp, tn, fn = counts["TP"], counts["FP"], counts["TN"], counts["FN"]
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    do_nothing_acc = tn / (tn + fp) if (tn + fp) else None
    lat = sorted(c["actual"]["latency_ms"] for c in cases)

    def pct(p):
        if not lat:
            return None
        k = min(len(lat) - 1, int(round((p / 100) * (len(lat) - 1))))
        return lat[k]

    return {
        "scored_cases": len(cases),
        "total_cases": len(all_cases),
        "known_limitation_cases": len(all_cases) - len(cases),
        "passed": sum(c["passed"] for c in cases),
        "failed": sum(not c["passed"] for c in cases),
        "counts": counts,
        "intervention_precision": prec,
        "intervention_recall": rec,
        "do_nothing_accuracy": do_nothing_acc,
        "latency_ms": {
            "p50": pct(50), "p95": pct(95),
            "mean": round(statistics.fmean(lat), 2) if lat else None,
            "max": lat[-1] if lat else None,
        },
        "llm_calls_total": sum(c["actual"]["llm_calls"] for c in cases),
    }


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)


def write_report(results: dict) -> str:
    m = results["metrics"]
    cases = results["cases"]
    lines: list[str] = []
    add = lines.append

    add(f"# Kivi Phonetic Memory — Evaluation Report\n")
    add(f"- generated: `{results['generated_at']}`")
    add(f"- llm mode: `{results['llm_mode']}`  ·  total LLM calls: **{m['llm_calls_total']}**")
    add(f"- dataset: `{results['dataset']}`  ·  cases: **{m['total_cases']}** "
        f"({m['scored_cases']} scored + {m['known_limitation_cases']} known-limitation)")
    add(f"- **scored: passed {m['passed']} / {m['scored_cases']}**  ·  failed: {m['failed']}")
    add(f"- db file after full run (all {m['total_cases']} cases, one utterance each): {results['db_bytes']:,} bytes\n")

    add("## Headline metrics\n")
    add("_Computed over the scored cases. Known-limitation cases are excluded here "
        "and listed in their own section so they cannot skew the numbers._\n")
    add("| metric | value | reading |")
    add("|---|---|---|")
    add(f"| intervention precision | **{_fmt(m['intervention_precision'])}** | of the rewrites Kivi made, how many were the right call |")
    add(f"| intervention recall | **{_fmt(m['intervention_recall'])}** | of the rewrites it should have made, how many it made |")
    add(f"| do-nothing accuracy | **{_fmt(m['do_nothing_accuracy'])}** | of the sentences it should have left alone, how many it did |")
    add(f"| latency p50 / p95 | {m['latency_ms']['p50']} ms / {m['latency_ms']['p95']} ms | mock LLM; add model latency for `--live` |")
    add(f"| LLM calls (whole suite) | {m['llm_calls_total']} | mock mode issues none; `--live` issues one per utterance |")
    c = m["counts"]
    add(f"\nOutcome mix (scored): TP {c['TP']} · FP {c['FP']} · TN {c['TN']} · FN {c['FN']} · "
        f"ambiguous handled {c['AMB_OK']} · ambiguous mishandled {c['AMB_BAD']}\n")

    scored = [c for c in cases if not c["known_limitation"]]

    def ledger(title: str, predicate, pool=None) -> None:
        rows = [c for c in (pool if pool is not None else scored) if predicate(c)]
        add(f"## {title} ({len(rows)})\n")
        if not rows:
            add("_none_\n")
            return
        add("| case | input (formatted) | → memory-aware | reason | notes |")
        add("|---|---|---|---|---|")
        for c in rows:
            applied = [d for d in c["actual"]["decisions"] if d["action"] == "apply"]
            skipped = [d for d in c["actual"]["decisions"] if d["action"] == "skip"]
            reason = ", ".join(sorted({d["reason_tag"] for d in (applied or skipped)})) or "—"
            note = "" if c["passed"] else f"**FAIL** (expected `{c['expected']['memory_aware']}`)"
            add(f"| `{c['id']}` | {c['inputs']['formatted']} | {c['actual']['memory_aware_text']} | `{reason}` | {note} |")
        add("")

    ledger("Useful interventions", lambda c: c["outcome"] == "TP")
    ledger("Unnecessary or incorrect interventions",
           lambda c: c["outcome"] == "FP" or (c["clazz"] == "should_intervene" and not c["passed"]))
    ledger("Correct restraint (did nothing, on purpose)",
           lambda c: c["outcome"] in ("TN", "AMB_OK"))

    kl = [c for c in cases if c["known_limitation"]]
    add(f"## Known limitations ({len(kl)})\n")
    add("_Documented design boundaries of a word-level phonetic memory. Kept in "
        "the suite so they stay visible; excluded from the headline metrics._\n")
    for c in kl:
        add(f"### `{c['id']}` — {'handled as intended' if c['passed'] else 'diverges from the ideal'}")
        add(f"- {c['description']}")
        add(f"- input:    `{c['inputs']['formatted']}`")
        add(f"- ideal:    `{c['expected']['memory_aware']}`")
        add(f"- actual:   `{c['actual']['memory_aware_text']}`")
        add("")

    add("## Every case\n")
    add("| case | class | outcome | pass | latency | reason tags |")
    add("|---|---|---|:--:|---:|---|")
    for c in cases:
        tags = ", ".join(f"{d['action']}:{d['reason_tag']}" for d in c["actual"]["decisions"]) or "—"
        add(f"| `{c['id']}` | {c['clazz']} | {c['outcome']} | "
            f"{'✅' if c['passed'] else '❌'} | {c['actual']['latency_ms']} ms | {tags} |")
    add("")

    failures = [c for c in cases if not c["passed"] and not c["known_limitation"]]
    if failures:
        add("## Scored failures in detail\n")
        for c in failures:
            add(f"### `{c['id']}` — {c['description']}")
            add(f"- expected: `{c['expected']['memory_aware']}` (intervened={c['expected'].get('intervened')})")
            add(f"- actual:   `{c['actual']['memory_aware_text']}` (intervened={c['actual']['intervened']})")
            if c["expected"].get("reason"):
                add(f"- expected reason tag `{c['expected']['reason']}`; got {sorted({d['reason_tag'] for d in c['actual']['decisions']})}")
            add("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="use the real Anthropic API")
    parser.add_argument("--case", help="run only the case with this id, printed verbosely")
    parser.add_argument("--dataset", default=str(DATASET))
    args = parser.parse_args(argv)

    _prepare_env(live=args.live)
    # Import AFTER env is set so config picks up the eval DB / llm mode.
    from app.db.migrate import migrate

    migrate()

    dataset = yaml.safe_load(Path(args.dataset).read_text(encoding="utf-8"))
    cases_spec = dataset["cases"]
    if args.case:
        cases_spec = [c for c in cases_spec if c["id"] == args.case]
        if not cases_spec:
            print(f"no such case: {args.case}", file=sys.stderr)
            return 2

    results = [run_case(c) for c in cases_spec]

    if args.case:
        print(json.dumps(results[0], indent=2, default=str))
        return 0 if results[0]["passed"] else 1

    from app.db.models import db_file_size_bytes

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "llm_mode": os.environ["KIVI_LLM_MODE"],
        "dataset": os.path.relpath(args.dataset, REPO_ROOT).replace("\\", "/"),
        "db_bytes": db_file_size_bytes(),
        "metrics": _metrics(results),
        "cases": results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "results.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    (RESULTS_DIR / "report.md").write_text(write_report(payload), encoding="utf-8")

    for f in (EVAL_DB, EVAL_DB + "-wal", EVAL_DB + "-shm", EVAL_DB + "-journal"):
        Path(f).unlink(missing_ok=True)

    m = payload["metrics"]
    kl_failed = [c for c in results if c["known_limitation"] and not c["passed"]]
    print(f"scored cases    : {m['scored_cases']}  (+{m['known_limitation_cases']} known-limitation)")
    print(f"scored passed   : {m['passed']}  failed: {m['failed']}")
    print(f"precision       : {_fmt(m['intervention_precision'])}")
    print(f"recall          : {_fmt(m['intervention_recall'])}")
    print(f"do-nothing acc  : {_fmt(m['do_nothing_accuracy'])}")
    print(f"latency p50/p95 : {m['latency_ms']['p50']} / {m['latency_ms']['p95']} ms  (mock LLM)")
    print(f"llm calls       : {m['llm_calls_total']}")
    print(f"known-limits    : {len(kl_failed)} diverge from ideal as documented")
    print(f"results         : eval/results/results.json")
    print(f"report          : eval/results/report.md")
    return 0 if m["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
