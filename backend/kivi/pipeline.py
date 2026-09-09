"""End-to-end orchestrator:

  input -> ASR -> formatter -> spans -> retrieval -> context -> decision
        -> rewrite -> memory-aware output -> decision trace

Read-only with respect to memory: processing never writes memory/alias/evidence.
It only writes `request` + `decision` rows (history / explainability).
"""
from __future__ import annotations

import time

from kivi.asr import get_asr
from kivi.formatter import get_formatter
from kivi.spans import build_spans
from kivi.context import utterance_context, assess
from kivi.memory.retrieval import find_candidates
from kivi.decision import decide
from kivi.rewrite import apply_replacements
from kivi.explain import build_trace, summarize
from kivi.db.store import txn, insert_request, insert_decision


def process(*, text: str | None = None, audio_path: str | None = None,
            asr_provider: str | None = None, formatter_mode: str | None = None,
            persist: bool = True) -> dict:
    t0 = time.perf_counter()
    asr = get_asr(asr_provider)
    fmt = get_formatter(formatter_mode)

    # ---- LEVEL 1: ASR ----
    if audio_path:
        asr_res = asr.transcribe_audio(audio_path)
        input_type = "audio"
    else:
        asr_res = asr.transcribe_text(text or "")
        input_type = "text"

    # ---- LEVEL 2: formatted ----
    fmt_res = fmt.format(asr_res.text)

    # ---- LEVEL 3: memory-aware ----
    decisions = []
    with txn() as conn:
        spans = build_spans(fmt_res.text, asr_res.text)
        for sp in spans:
            cands = find_candidates(conn, sp.text, sp.asr_original)
            ctx = utterance_context(fmt_res.text, exclude=sp.text)
            scored = []
            for c in cands:
                mem = conn.execute("SELECT * FROM memory WHERE id = ?", (c.memory_id,)).fetchone()
                a = assess(mem, ctx)
                scored.append({"cand": c, **a})
            d = decide(sp.text, sp.start, sp.end, sp.asr_original, scored)
            d.context_domain = ctx["domain"]
            decisions.append(d)

        memory_aware = apply_replacements(fmt_res.text, decisions)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        model_calls = asr_res.model_calls + fmt_res.model_calls
        est_cost = round(asr_res.est_cost_usd + fmt_res.est_cost_usd, 6)

        request_id = None
        if persist:
            request_id = insert_request(
                conn, input_type=input_type, audio_ref=audio_path,
                asr_provider=asr_res.provider, asr_text=asr_res.text,
                formatter_provider=fmt_res.provider, formatted_text=fmt_res.text,
                memory_aware_text=memory_aware, latency_ms=latency_ms,
                model_calls=model_calls, est_cost_usd=est_cost,
            )
            for d in decisions:
                if not d.candidate_memory_id and d.action == "KEEP":
                    continue  # don't store the no-op spans
                did = insert_decision(
                    conn, request_id=request_id, span_text=d.span_text,
                    span_start=d.span_start, span_end=d.span_end, asr_original=d.asr_original,
                    candidate_memory_id=d.candidate_memory_id, match_method=d.match_method,
                    s_surf=d.s_surf, s_ctx_pos=d.s_ctx_pos, s_ctx_neg=d.s_ctx_neg, s_ctx=d.s_ctx,
                    mem_confidence=d.mem_confidence, combined_score=d.combined_score,
                    ambiguity_flag=int(d.ambiguity_flag), contradiction_flag=int(d.contradiction_flag),
                    action=d.action, reason_code=d.reason_code, reason_text=d.reason_text,
                    s_personal=d.s_personal, personal_note=(d.personal_note or None),
                )
                d.decision_id = did

        trace = build_trace(conn, [d for d in decisions if d.candidate_memory_id or d.action != "KEEP"])

    return {
        "request_id": request_id,
        "input_type": input_type,
        "asr_text": asr_res.text,
        "formatted_text": fmt_res.text,
        "memory_aware_text": memory_aware,
        "trace": trace,
        "summary": summarize(decisions),
        "decisions": [
            {
                "decision_id": getattr(d, "decision_id", None),
                "span": d.span_text, "action": d.action, "reason_code": d.reason_code,
                "reason": d.reason_text, "matched_memory": d.candidate_canonical,
                "asr_original": d.asr_original, "context_domain": getattr(d, "context_domain", None),
                "replacement": d.replacement,
                "personal": {
                    "method_personal": d.match_method == "personal",
                    "s_personal": d.s_personal,
                    "misheard_count": d.personal_prior_n,
                    "rules": d.personal_rules,
                    "note": d.personal_note or None,
                },
            }
            for d in decisions if d.candidate_memory_id or d.action != "KEEP"
        ],
        "metrics": {
            "latency_ms": latency_ms,
            "model_calls": model_calls,
            "est_cost_usd": est_cost,
            "asr_provider": asr_res.provider,
            "formatter_provider": fmt_res.provider,
        },
    }
