"""Evaluation harness.

For every case:
  1. reset DB to seed
  2. apply `setup` observations (if any)
  3. run the pipeline
  4. compare memory-aware output + the decision for the target span
  5. record output, decision, scores, latency, and a failure category on miss

Writes:
  evaluation/results/summary.json
  evaluation/results/report.md
  evaluation/results/cases/<id>.json
  evaluation/results/failures/<id>.json   (only for failures)

Deterministic: echo ASR + rules formatter + fixed config -> identical results each run.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from statistics import quantiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from kivi.config import EVAL_RESULTS_DIR  # noqa: E402
from kivi.db.reset import reset  # noqa: E402
from kivi.db.store import connect, get_memory_by_norm, table_counts  # noqa: E402
from kivi.normalization import normalize_token  # noqa: E402
from kivi.memory.learning import observe  # noqa: E402
from kivi.pipeline import process  # noqa: E402

DATASET = ROOT / "evaluation" / "dataset" / "cases.jsonl"


def _load_cases() -> list[dict]:
    out = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _decision_for_span(result: dict, span: str) -> dict | None:
    target = normalize_token(span)
    for d in result["decisions"]:
        if normalize_token(d["span"]) == target:
            return d
    return None


def _failure_category(expected_action, actual_action, expected_out, actual_out) -> str:
    if expected_action == "KEEP" and actual_action == "REPLACE":
        return "over_intervention"
    if expected_action == "REPLACE" and actual_action in ("KEEP", None):
        return "missed_intervention"
    if expected_action == "REPLACE" and actual_action == "DEFER":
        return "under_confident"
    if expected_action == "DEFER" and actual_action == "REPLACE":
        return "over_confident"
    if expected_action == "DEFER" and actual_action in ("KEEP", None):
        return "missed_defer"
    if expected_action == "KEEP" and actual_action == "DEFER":
        return "spurious_defer"
    if expected_out != actual_out:
        return "output_mismatch"
    return "other"


def run_eval() -> dict:
    cases = _load_cases()
    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_RESULTS_DIR / "cases").mkdir(exist_ok=True)
    (EVAL_RESULTS_DIR / "failures").mkdir(exist_ok=True)
    # clear stale failures
    for f in (EVAL_RESULTS_DIR / "failures").glob("*.json"):
        f.unlink()

    results = []
    latencies = []

    for case in cases:
        reset()

        # setup observations
        for obs in case.get("setup", []):
            observe(**obs)

        # capture memory state for stability check
        stability_target = case.get("check_stability")
        conf_before = None
        if stability_target:
            conn = connect()
            try:
                m = get_memory_by_norm(conn, normalize_token(stability_target))
                conf_before = m["confidence"] if m else None
            finally:
                conn.close()

        counts_before = None
        repeat = int(case.get("repeat", 1))
        outputs = []
        first_result = None
        for i in range(repeat):
            if i == 1:
                conn = connect()
                try:
                    counts_before = table_counts(conn)
                finally:
                    conn.close()
            res = process(text=case["input"], persist=True)
            outputs.append(res["memory_aware_text"])
            if first_result is None:
                first_result = res
        result = first_result
        latencies.append(result["metrics"]["latency_ms"])

        actual_out = result["memory_aware_text"]
        dec = _decision_for_span(result, case["target_span"])
        actual_action = dec["action"] if dec else "KEEP"

        output_ok = actual_out == case["expected_output"]
        action_ok = actual_action == case["expected_action"]

        reason_needle = case.get("expect_reason_contains")
        reason_ok = None
        if reason_needle:
            reason_ok = bool(dec) and reason_needle.lower() in dec["reason"].lower()

        stability_ok = None
        if stability_target:
            conn = connect()
            try:
                m = get_memory_by_norm(conn, normalize_token(stability_target))
                conf_after = m["confidence"] if m else None
            finally:
                conn.close()
            stability_ok = (conf_before == conf_after)

        idempotency_ok = None
        if repeat > 1:
            idempotency_ok = len(set(outputs)) == 1
            conn = connect()
            try:
                counts_after = table_counts(conn)
            finally:
                conn.close()
            grew = {k: counts_after[k] - counts_before[k] for k in counts_after}
            idempotency_ok = idempotency_ok and grew["memory"] == 0 and grew["alias"] == 0 \
                and grew["evidence"] == 0 and grew.get("sound_pattern", 0) == 0

        passed = output_ok and action_ok and (stability_ok is not False) \
            and (idempotency_ok is not False) and (reason_ok is not False)

        row = {
            "id": case["id"],
            "category": case["category"],
            "description": case["description"],
            "input": case["input"],
            "expected_output": case["expected_output"],
            "actual_output": actual_out,
            "expected_action": case["expected_action"],
            "actual_action": actual_action,
            "reason": dec["reason"] if dec else "no candidate matched this span",
            "scores": next(
                (t["scores"] for t in result["trace"]
                 if normalize_token(t["span"]) == normalize_token(case["target_span"])),
                None,
            ),
            "asr_text": result["asr_text"],
            "formatted_text": result["formatted_text"],
            "memory_aware_text": actual_out,
            "output_ok": output_ok,
            "action_ok": action_ok,
            "stability_ok": stability_ok,
            "idempotency_ok": idempotency_ok,
            "reason_ok": reason_ok,
            "expect_reason_contains": reason_needle,
            "personal": next(
                (t.get("personal") for t in result["trace"]
                 if normalize_token(t["span"]) == normalize_token(case["target_span"])),
                None,
            ),
            "passed": passed,
            "latency_ms": result["metrics"]["latency_ms"],
            "model_calls": result["metrics"]["model_calls"],
            "est_cost_usd": result["metrics"]["est_cost_usd"],
        }
        if not passed:
            row["failure_category"] = _failure_category(
                case["expected_action"], actual_action, case["expected_output"], actual_out
            )
        results.append(row)
        (EVAL_RESULTS_DIR / "cases" / f"{case['id']}.json").write_text(
            json.dumps(row, indent=2), encoding="utf-8"
        )
        if not passed:
            (EVAL_RESULTS_DIR / "failures" / f"{case['id']}.json").write_text(
                json.dumps(row, indent=2), encoding="utf-8"
            )

    summary = _summarize(results, latencies)
    (EVAL_RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (EVAL_RESULTS_DIR / "report.md").write_text(_report_md(summary, results), encoding="utf-8")
    reset()  # leave the DB in a clean seeded state for the demo
    return summary


def _summarize(results, latencies) -> dict:
    total = len(results)
    passed = sum(r["passed"] for r in results)

    exp_replace = [r for r in results if r["expected_action"] == "REPLACE"]
    act_replace = [r for r in results if r["actual_action"] == "REPLACE"]
    tp = sum(1 for r in act_replace if r["expected_action"] == "REPLACE")
    precision = tp / len(act_replace) if act_replace else 1.0
    recall = tp / len(exp_replace) if exp_replace else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    keep_cases = [r for r in results if r["expected_action"] == "KEEP"]
    defer_cases = [r for r in results if r["expected_action"] == "DEFER"]
    non_interv_acc = (sum(r["action_ok"] for r in keep_cases) / len(keep_cases)) if keep_cases else 1.0
    defer_acc = (sum(r["action_ok"] for r in defer_cases) / len(defer_cases)) if defer_cases else 1.0

    over_interv = sum(1 for r in results
                      if r["expected_action"] == "KEEP" and r["actual_action"] == "REPLACE")
    stability = [r for r in results if r["stability_ok"] is not None]
    idem = [r for r in results if r["idempotency_ok"] is not None]

    lat_sorted = sorted(latencies)
    p95 = lat_sorted[max(0, int(round(0.95 * (len(lat_sorted) - 1))))] if lat_sorted else 0.0

    pp_cases = [r for r in results if r["category"] == "personal_phonetics"]
    pp_by_rule = {
        "nomination (accent rule creates the candidate)":
            [r["id"] for r in pp_cases
             if (r.get("personal") or {}).get("method_personal")],
        "prior (history lifts a borderline match)":
            [r["id"] for r in pp_cases
             if (r.get("personal") or {}).get("misheard_count", 0) > 0
             and not (r.get("personal") or {}).get("method_personal")
             and r["expected_action"] == "REPLACE"],
        "safety (accent signal must not override KEEP)":
            [r["id"] for r in pp_cases if r["expected_action"] == "KEEP"],
    }
    personal_phonetics = {
        "cases": len(pp_cases),
        "passed": sum(r["passed"] for r in pp_cases),
        "reason_assertions_pass": f"{sum(1 for r in results if r['reason_ok'])}/"
                                  f"{sum(1 for r in results if r['reason_ok'] is not None)}",
        "demonstrates": {k: v for k, v in pp_by_rule.items() if v},
        "note": "Accent profile starts empty; every personal_phonetics case learns its "
                "rules from `setup` corrections before the pipeline runs. It never "
                "overrides a deliberate KEEP or a not-yet-active memory.",
    }

    return {
        "headline": {
            "cases": total,
            "passed": passed,
            "pass_rate": round(passed / total, 4) if total else 1.0,
            "action_accuracy": round(sum(r["action_ok"] for r in results) / total, 4) if total else 1.0,
            "exact_output_match_rate": round(sum(r["output_ok"] for r in results) / total, 4) if total else 1.0,
            "intervention_precision": round(precision, 4),
            "intervention_recall": round(recall, 4),
            "intervention_f1": round(f1, 4),
            "non_intervention_accuracy": round(non_interv_acc, 4),
            "defer_accuracy": round(defer_acc, 4),
            "over_intervention_count": over_interv,
            "memory_stability_pass": f"{sum(r['stability_ok'] for r in stability)}/{len(stability)}",
            "idempotency_pass": f"{sum(r['idempotency_ok'] for r in idem)}/{len(idem)}",
        },
        "latency_ms": {
            "p50": round(quantiles(latencies, n=2)[0], 3) if len(latencies) > 1 else (latencies[0] if latencies else 0.0),
            "p95": round(p95, 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "model_usage": {
            "total_model_calls": sum(r["model_calls"] for r in results),
            "total_est_cost_usd": round(sum(r["est_cost_usd"] for r in results), 6),
            "note": "0 by design: echo ASR + rule-based formatter, no LLM in the core path",
        },
        "personal_phonetics": personal_phonetics,
        "by_category": _by_category(results),
        "failures": [
            {"id": r["id"], "category": r["category"],
             "failure_category": r.get("failure_category"),
             "expected": r["expected_action"], "actual": r["actual_action"],
             "expected_output": r["expected_output"], "actual_output": r["actual_output"]}
            for r in results if not r["passed"]
        ],
    }


def _by_category(results) -> dict:
    cats: dict[str, dict] = {}
    for r in results:
        c = cats.setdefault(r["category"], {"total": 0, "passed": 0})
        c["total"] += 1
        c["passed"] += int(r["passed"])
    return cats


def _report_md(summary, results) -> str:
    h = summary["headline"]
    lines = [
        "# Kivi Personal Phonetic Memory - Evaluation Report",
        "",
        "_Deterministic run: echo ASR + rule-based formatter + fixed `config.json`._",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cases | {h['cases']} |",
        f"| Passed | {h['passed']} ({h['pass_rate']*100:.1f}%) |",
        f"| Action accuracy | {h['action_accuracy']*100:.1f}% |",
        f"| Exact output match | {h['exact_output_match_rate']*100:.1f}% |",
        f"| **Intervention precision** | **{h['intervention_precision']*100:.1f}%** |",
        f"| Intervention recall | {h['intervention_recall']*100:.1f}% |",
        f"| Intervention F1 | {h['intervention_f1']*100:.1f}% |",
        f"| **Non-intervention accuracy** | **{h['non_intervention_accuracy']*100:.1f}%** |",
        f"| Defer accuracy | {h['defer_accuracy']*100:.1f}% |",
        f"| Over-intervention count | {h['over_intervention_count']} |",
        f"| Memory-stability pass | {h['memory_stability_pass']} |",
        f"| Idempotency pass | {h['idempotency_pass']} |",
        "",
        "## Latency / model usage / cost",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Latency p50 | {summary['latency_ms']['p50']} ms |",
        f"| Latency p95 | {summary['latency_ms']['p95']} ms |",
        f"| Latency max | {summary['latency_ms']['max']} ms |",
        f"| Total model calls | {summary['model_usage']['total_model_calls']} |",
        f"| Total est. cost | ${summary['model_usage']['total_est_cost_usd']} |",
        "",
        f"> {summary['model_usage']['note']}",
        "",
        "## By category",
        "",
        "| Category | Passed / Total |",
        "|---|---|",
    ]
    for cat, v in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {v['passed']} / {v['total']} |")

    pp = summary.get("personal_phonetics", {})
    if pp.get("cases"):
        lines += [
            "", "## Personal (accent-adaptive) phonetics", "",
            f"- cases: **{pp['passed']} / {pp['cases']}** passed",
            f"- reason-string assertions: **{pp['reason_assertions_pass']}**",
            f"- {pp['note']}", "",
            "| What it demonstrates | Cases |", "|---|---|",
        ]
        for k, v in pp.get("demonstrates", {}).items():
            lines.append(f"| {k} | {', '.join(v)} |")

    lines += ["", "## Per-case results", "",
              "| ID | Category | Expected | Actual | Output OK | Pass | Reason |",
              "|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['category']} | {r['expected_action']} | {r['actual_action']} | "
            f"{'yes' if r['output_ok'] else 'NO'} | {'PASS' if r['passed'] else 'FAIL'} | "
            f"{r['reason'][:90].replace('|', '/')} |"
        )

    fails = [r for r in results if not r["passed"]]
    lines += ["", "## Failures", ""]
    if not fails:
        lines.append("_None - all cases passed._")
    else:
        for r in fails:
            lines += [
                f"### {r['id']} ({r['category']}) - {r.get('failure_category')}",
                "",
                f"- input: `{r['input']}`",
                f"- expected: `{r['expected_output']}` / **{r['expected_action']}**",
                f"- actual:   `{r['actual_output']}` / **{r['actual_action']}**",
                f"- scores: `{r['scores']}`",
                f"- reason: {r['reason']}",
                "",
            ]
    lines.append("")
    lines.append(f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S')} local._")
    return "\n".join(lines)


if __name__ == "__main__":
    s = run_eval()
    print(json.dumps(s["headline"], indent=2))
    print("latency:", s["latency_ms"])
