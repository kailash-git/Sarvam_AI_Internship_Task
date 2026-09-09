"""HTTP surface. Thin adapters over the service layer; no logic lives here."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services import admin, learning, repo
from app.services.llm import format_from_asr
from app.services.pipeline import process

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------- schemas

class CorrectionIn(BaseModel):
    asr_text: str = ""
    formatted_text: str
    corrected_text: str
    category: str = "other"
    note: str = ""


class DictionaryIn(BaseModel):
    canonical: str
    category: str = "other"
    aliases: list[str] = Field(default_factory=list)
    note: str = ""


class RejectionIn(BaseModel):
    entry_id: int
    note: str = ""


class AcceptanceIn(BaseModel):
    entry_id: int


class FormatIn(BaseModel):
    asr_text: str = ""
    formatted_text: str
    persist: bool = True


class FromAsrIn(BaseModel):
    asr_text: str


class EntryPatch(BaseModel):
    status: str | None = None
    category: str | None = None
    note: str | None = None
    canonical: str | None = None


class ResetIn(BaseModel):
    seed: bool = True


# --------------------------------------------------------------------- routes

@router.get("/health")
def health() -> dict:
    return {"ok": True, "llm_mode": settings.llm_mode, "db": repo.stats()}


@router.get("/stats")
def stats() -> dict:
    return repo.stats()


@router.get("/memory")
def memory(status: str | None = None) -> dict:
    return {"entries": repo.list_entries(status=status), "stats": repo.stats()}


@router.get("/memory/{entry_id}")
def memory_detail(entry_id: int) -> dict:
    entry = repo.get_entry(entry_id)
    if not entry:
        raise HTTPException(404, f"no entry {entry_id}")
    entry["observations"] = repo.observations_for_entry(entry_id)
    return entry


@router.patch("/memory/{entry_id}")
def memory_patch(entry_id: int, patch: EntryPatch) -> dict:
    if not repo.get_entry(entry_id):
        raise HTTPException(404, f"no entry {entry_id}")
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if fields.get("status") and fields["status"] not in repo.STATUSES:
        raise HTTPException(422, f"status must be one of {repo.STATUSES}")
    if fields.get("category") and fields["category"] not in repo.CATEGORIES:
        raise HTTPException(422, f"category must be one of {repo.CATEGORIES}")
    return repo.update_entry(entry_id, **fields)


@router.delete("/memory/{entry_id}")
def memory_delete(entry_id: int) -> dict:
    if not repo.delete_entry(entry_id):
        raise HTTPException(404, f"no entry {entry_id}")
    return {"deleted": entry_id}


@router.post("/observations/correction")
def obs_correction(body: CorrectionIn) -> dict:
    res = learning.learn_from_correction(**body.model_dump())
    return {"changes": [asdict(c) for c in res.changes], "notes": res.notes}


@router.post("/observations/dictionary")
def obs_dictionary(body: DictionaryIn) -> dict:
    res = learning.learn_from_dictionary(**body.model_dump())
    return {"changes": [asdict(c) for c in res.changes], "notes": res.notes}


@router.post("/observations/rejection")
def obs_rejection(body: RejectionIn) -> dict:
    res = learning.learn_from_rejection(**body.model_dump())
    return {"changes": [asdict(c) for c in res.changes], "notes": res.notes}


@router.post("/observations/acceptance")
def obs_acceptance(body: AcceptanceIn) -> dict:
    res = learning.learn_from_acceptance(**body.model_dump())
    return {"changes": [asdict(c) for c in res.changes], "notes": res.notes}


@router.post("/format")
def format_route(body: FormatIn) -> dict:
    r = process(body.asr_text, body.formatted_text, persist=body.persist)
    return {
        "asr_text": r.asr_text,
        "formatted_text": r.formatted_text,
        "memory_aware_text": r.memory_aware_text,
        "intervened": r.intervened,
        "utterance_id": r.utterance_id,
        "decisions": [asdict(d) for d in r.decisions],
        "trace": r.trace,
    }


@router.post("/format/from-asr")
def from_asr(body: FromAsrIn) -> dict:
    return {"formatted_text": format_from_asr(body.asr_text)}


@router.get("/utterances")
def utterances(limit: int = 25) -> dict:
    return {"utterances": repo.recent_utterances(limit=limit)}


@router.post("/reset")
def reset(body: ResetIn) -> dict:
    return admin.reset(seed=body.seed)
