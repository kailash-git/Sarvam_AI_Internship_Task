"""HTTP surface for the Kivi personal phonetic memory prototype."""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from kivi.config import (
    FRONTEND_DIR, EVAL_RESULTS_DIR, UPLOAD_DIR, AUDIO, as_dict, ASR_PROVIDER,
)
from kivi.db.migrate import migrate
from kivi.db.reset import reset as db_reset
from kivi.db.store import (
    connect, list_memories, get_memory, list_aliases, list_evidence,
    list_observations, load_json, list_decisions, get_request, table_counts,
    list_sound_patterns,
)
from kivi.memory.phonetic_profile import rule_label
from kivi.pipeline import process
from kivi.memory.learning import observe

app = FastAPI(title="Kivi Personal Phonetic Memory", version="0.1.0")


@app.on_event("startup")
def _startup():
    migrate()
    conn = connect()
    try:
        empty = conn.execute("SELECT COUNT(*) AS c FROM memory").fetchone()["c"] == 0
    finally:
        conn.close()
    if empty:
        db_reset()


# ---------- models ----------

class ProcessIn(BaseModel):
    text: str | None = None
    asr_provider: str | None = None


class ObserveIn(BaseModel):
    type: str
    chosen_form: str
    rejected_form: str | None = None
    asr_original: str | None = None
    raw_asr_text: str | None = None
    formatted_text: str | None = None
    context: dict | None = None
    entity_type: str | None = None
    decision_id: int | None = None


class TeachIn(BaseModel):
    canonical_form: str
    entity_type: str = "term"
    positive_keywords: list[str] = []
    negative_keywords: list[str] = []
    domain: str | None = None


# ---------- routes ----------

@app.get("/api/health")
def health():
    conn = connect()
    try:
        counts = table_counts(conn)
    finally:
        conn.close()
    return {"status": "ok", "config": as_dict(), "counts": counts}


@app.post("/api/process")
def api_process(body: ProcessIn):
    if not body.text or not body.text.strip():
        raise HTTPException(400, "text is required (audio upload uses /api/process-audio)")
    return process(text=body.text, asr_provider=body.asr_provider)


@app.post("/api/process-audio")
async def api_process_audio(audio: UploadFile = File(...), asr_provider: str = Form(None)):
    provider = asr_provider or ASR_PROVIDER
    if provider in ("echo",):
        raise HTTPException(
            409,
            "Live/recorded audio needs a real ASR provider. Set asr_provider='whisper' "
            "(local faster-whisper) or 'fixture'. 'echo' only handles typed text.",
        )
    data = await audio.read()
    if len(data) > AUDIO["max_mb"] * 1024 * 1024:
        raise HTTPException(413, f"audio exceeds {AUDIO['max_mb']} MB")
    if not data:
        raise HTTPException(422, "empty audio")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    import hashlib
    ref = hashlib.sha1(data).hexdigest()[:16]
    ext = Path(audio.filename or "rec.webm").suffix or ".webm"
    path = UPLOAD_DIR / f"{ref}{ext}"
    path.write_bytes(data)
    try:
        return process(audio_path=str(path), asr_provider=provider)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@app.post("/api/transcribe")
def api_transcribe(body: ProcessIn):
    from kivi.asr import get_asr
    if not body.text:
        raise HTTPException(400, "text required for this prototype endpoint")
    t0 = time.perf_counter()
    res = get_asr(body.asr_provider).transcribe_text(body.text)
    return {"text": res.text, "provider": res.provider,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}


@app.post("/api/observe")
def api_observe(body: ObserveIn):
    try:
        return observe(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/memory")
def api_teach(body: TeachIn):
    try:
        return observe(
            type="manual_teach", chosen_form=body.canonical_form,
            entity_type=body.entity_type,
            context={"keywords": body.positive_keywords, "domain": body.domain or "general"},
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/memory")
def api_list_memory():
    conn = connect()
    try:
        out = []
        for m in list_memories(conn):
            out.append({
                "id": m["id"], "canonical_form": m["canonical_form"],
                "entity_type": m["entity_type"], "status": m["status"],
                "confidence": m["confidence"],
                "aliases": [a["surface_form"] for a in list_aliases(conn, m["id"])],
            })
        return {"items": out, "count": len(out)}
    finally:
        conn.close()


@app.get("/api/memory/{memory_id}")
def api_memory_detail(memory_id: int):
    conn = connect()
    try:
        m = get_memory(conn, memory_id)
        if not m:
            raise HTTPException(404, "memory not found")
        return {
            "id": m["id"], "canonical_form": m["canonical_form"],
            "entity_type": m["entity_type"], "status": m["status"],
            "confidence": m["confidence"], "source": m["source"], "notes": m["notes"],
            "positive_contexts": load_json(m["positive_contexts"], {}),
            "negative_contexts": load_json(m["negative_contexts"], {}),
            "aliases": [dict(a) for a in list_aliases(conn, memory_id)],
            "evidence": [dict(e) for e in list_evidence(conn, memory_id)],
            "observations": [dict(o) for o in list_observations(conn, memory_id)],
        }
    finally:
        conn.close()


@app.delete("/api/memory/{memory_id}")
def api_deactivate(memory_id: int):
    from kivi.db.store import txn, update_memory
    with txn() as conn:
        if not get_memory(conn, memory_id):
            raise HTTPException(404, "memory not found")
        update_memory(conn, memory_id, status="inactive")
    return {"status": "ok", "memory_id": memory_id, "new_status": "inactive"}


@app.get("/api/phonetic-profile")
def api_phonetic_profile():
    """The user's learned accent profile: how THIS person's ASR mangles sounds."""
    from kivi.config import PP
    conn = connect()
    try:
        rows = [dict(r) for r in list_sound_patterns(conn)]
    finally:
        conn.close()
    active = int(PP.get("min_observations", 2))
    for r in rows:
        r["label"] = rule_label(r)
        r["active"] = r["observations"] >= active
    return {
        "rules": rows,
        "count": len(rows),
        "active_count": sum(1 for r in rows if r["active"]),
        "min_observations_to_activate": active,
        "note": "Learned from your corrections. A rule fires in retrieval once it has "
                "been seen at least min_observations times.",
    }


@app.get("/api/decisions")
def api_decisions(request_id: int | None = None):
    conn = connect()
    try:
        return {"items": [dict(d) for d in list_decisions(conn, request_id)]}
    finally:
        conn.close()


@app.get("/api/requests/{request_id}")
def api_request(request_id: int):
    conn = connect()
    try:
        r = get_request(conn, request_id)
        if not r:
            raise HTTPException(404, "request not found")
        return {"request": dict(r),
                "decisions": [dict(d) for d in list_decisions(conn, request_id)]}
    finally:
        conn.close()


@app.post("/api/admin/reset")
def api_reset():
    return db_reset()


@app.get("/api/evaluation/results")
def api_eval_results():
    summary = EVAL_RESULTS_DIR / "summary.json"
    report = EVAL_RESULTS_DIR / "report.md"
    if not summary.exists():
        raise HTTPException(404, "no evaluation results yet - run: python manage.py eval")
    return {
        "summary": json.loads(summary.read_text(encoding="utf-8")),
        "report_md": report.read_text(encoding="utf-8") if report.exists() else "",
    }


@app.get("/", response_class=HTMLResponse)
def index():
    idx = FRONTEND_DIR / "index.html"
    if idx.exists():
        return idx.read_text(encoding="utf-8")
    return "<h1>Kivi</h1><p>frontend/index.html missing</p>"
