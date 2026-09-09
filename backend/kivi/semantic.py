"""Optional semantic context layer.  Local, offline, deterministic, $0.

Why this exists
---------------
The rule-based `context.py` matches the utterance against small hand-listed
keyword sets ("ate", "fruit", ...).  A list can never enumerate every word that
signals a context - "Kivi is edible.", "Kivi is green and oval." slip through
because those words were not on the list, and the same gap exists for every
homophone pair (see/sea, Jon/John).

How it generalises
------------------
Each utterance is turned into a meaning vector.  Each memory builds *its own*
positive and negative prototype vector from the very sentences the user
confirmed / rejected it on (plus its stored keyword context, so seed memories
work immediately).  Comparing the utterance to those two prototypes says whether
this looks like a place the memory applies - without listing any of the words.

Two vectorisers, chosen by `config.json -> semantic_context.backend`:
  * "model2vec"  - a vendored static embedding model (backend/kivi/models/...).
                   Real semantic space: "crimson", "oval", "on the worktop" land
                   near "fruit / edible" with no curation.  ~0.1 ms/encode, pure
                   numpy, no network, no torch.
  * "lexicon"    - a shipped semantic-field JSON.  Zero dependencies.  Used
                   automatically as a fallback when the model / its dependency
                   is unavailable.

Scope
-----
This only feeds `context.assess`.  It never replaces the decision engine and, in
this version, only strengthens the *negative* (deliberate-KEEP) side - the side
the keyword list keeps missing.  Disabled -> behaviour is exactly the
keyword-only path.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from kivi import config as _config
from kivi.db.store import get_memory, list_observations, load_json
from kivi.normalization import content_tokens

_HERE = Path(__file__).resolve().parent
_LEX_PATH = _HERE / "data" / "semantic_fields.json"

# observation types that mean "the memory applied here" / "it must not apply here"
_POS_TYPES = {"explicit_correction", "confirmation", "manual_teach", "asr_pair"}
_NEG_TYPES = {"rejection", "rejection_global", "context_flag"}

_SUFFIXES = ("s", "es", "ed", "ing", "d")


# --------------------------------------------------------------------------- #
#  Vectoriser: model2vec (preferred) with automatic lexicon fallback
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _model():
    """Load the vendored static embedding model once, or return None to fall back."""
    if _config.SEM.get("backend", "model2vec") != "model2vec":
        return None
    try:
        from model2vec import StaticModel
    except Exception:
        return None
    path = _HERE.parents[1] / _config.SEM.get("model_path", "backend/kivi/models/potion-base-8M")
    if not path.exists():
        return None
    try:
        return StaticModel.from_pretrained(str(path))
    except Exception:
        return None


def active_backend() -> str:
    return "model2vec" if _model() is not None else "lexicon"


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, dict[str, float]]:
    """word -> {tag: weight}.  Built from the tag -> [words] file; multi-tag words accumulate."""
    raw = json.loads(_LEX_PATH.read_text(encoding="utf-8"))
    rev: dict[str, dict[str, float]] = {}
    for tag, words in raw.items():
        if tag.startswith("_") or not isinstance(words, list):
            continue
        for w in words:
            rev.setdefault(w, {})[tag] = rev.get(w, {}).get(tag, 0.0) + 1.0
    return rev


def _tags_for(tok: str) -> dict[str, float]:
    lex = _lexicon()
    if tok in lex:
        return lex[tok]
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            base = tok[: -len(suf)]
            if base in lex:
                return lex[base]
    return {}


def _l2(vec):
    if isinstance(vec, dict):
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {k: v / norm for k, v in vec.items()} if norm else {}
    norm = math.sqrt(float((vec * vec).sum()))
    return vec / norm if norm else vec


def concept_vector(text: str, exclude: str = ""):
    """Meaning vector for a piece of text.  numpy array (model) or {tag: weight} (lexicon)."""
    text = text or ""
    ex = (exclude or "").casefold().strip()
    m = _model()
    if m is not None:
        clean = text
        if ex:
            clean = re.sub(rf"\b{re.escape(ex)}\b", " ", clean, flags=re.IGNORECASE)
        return _l2(m.encode([clean])[0])
    acc: dict[str, float] = {}
    for tok in content_tokens(text):
        if tok == ex:
            continue
        for tag, w in _tags_for(tok).items():
            acc[tag] = acc.get(tag, 0.0) + w
    return _l2(acc)


def _empty(vec) -> bool:
    return len(vec) == 0 if isinstance(vec, dict) else not bool(getattr(vec, "size", 0))


def _cos(a, b) -> float:
    if _empty(a) or _empty(b):
        return 0.0
    if isinstance(a, dict):
        return sum(v * b.get(k, 0.0) for k, v in a.items())
    return float((a * b).sum())


def _add(acc, vec):
    if isinstance(vec, dict):
        for k, v in vec.items():
            acc[k] = acc.get(k, 0.0) + v
        return acc
    return vec if acc is None else acc + vec


# --------------------------------------------------------------------------- #
#  Per-memory prototypes  (cached by memory id + last-updated timestamp)
# --------------------------------------------------------------------------- #

_proto_cache: dict[tuple, object] = {}


def _prototype(conn, memory_id: int, canonical: str, polarity: str):
    mem = get_memory(conn, memory_id)
    if mem is None:
        return {} if _model() is None else None
    # NOTE: memory ids are reused after a reset, and `updated_at` has only
    # second resolution - so (id, updated_at) alone collides between two
    # different memories created in the same second and hands back a stale
    # prototype. Key on the identity and the stored contexts as well.
    field = "positive_contexts" if polarity == "pos" else "negative_contexts"
    key = (active_backend(), memory_id, mem["canonical_form"], mem["created_at"],
           mem["updated_at"], mem[field], polarity)
    if key in _proto_cache:
        return _proto_cache[key]

    types = _POS_TYPES if polarity == "pos" else _NEG_TYPES
    acc = None if _model() is not None else {}

    for o in list_observations(conn, memory_id):
        if o["type"] not in types:
            continue
        text = " ".join(x for x in (o["formatted_text"], o["raw_asr_text"]) if x)
        if not text:
            snap = load_json(o["context_snapshot"], {})
            text = " ".join(snap.get("keywords", []))
        if text.strip():
            acc = _add(acc, concept_vector(text, exclude=canonical))

    kw = load_json(mem[field], {}).get("keywords", [])
    if kw:
        acc = _add(acc, concept_vector(" ".join(kw), exclude=canonical))

    proto = _l2(acc) if acc is not None else ({} if _model() is None else None)
    if proto is None:
        proto = {}
    _proto_cache[key] = proto
    return proto


def _dominant_tag(vec) -> str:
    return max(vec, key=vec.get) if isinstance(vec, dict) and vec else ""


# --------------------------------------------------------------------------- #
#  Public entry point
# --------------------------------------------------------------------------- #

def semantic_context(conn, memory_row, full_text: str, exclude: str = "") -> dict:
    """Score the utterance against this memory's learned prototypes.

    Returns {active, backend, s_pos, s_neg, s_sem, note}.  s_pos / s_neg are
    cosine similarities; s_sem = s_pos - s_neg is the signed separation the
    caller acts on.
    """
    off = {"active": False, "backend": "none", "s_pos": 0.0, "s_neg": 0.0,
           "s_sem": 0.0, "note": ""}
    if not _config.SEM.get("enabled", False):
        return off

    sent = concept_vector(full_text, exclude=exclude)
    be = active_backend()
    if _empty(sent):
        return {**off, "active": True, "backend": be}

    pos = _prototype(conn, memory_row["id"], memory_row["canonical_form"], "pos")
    neg = _prototype(conn, memory_row["id"], memory_row["canonical_form"], "neg")
    s_pos = round(_cos(sent, pos), 4)
    s_neg = round(_cos(sent, neg), 4)
    s_sem = round(s_pos - s_neg, 4)

    note = ""
    mg = float(_config.SEM.get("margin", 0.1))
    if abs(s_sem) >= mg and (not _empty(pos) or not _empty(neg)):
        canon = memory_row["canonical_form"]
        if s_sem < 0:
            note = (f"Semantic context ({be}): the sentence resembles "
                    f"'{canon}'s rejected examples more than its confirmed ones "
                    f"(applied {s_pos:+.2f} vs rejected {s_neg:+.2f}).")
        else:
            note = (f"Semantic context ({be}): the sentence resembles "
                    f"'{canon}'s confirmed examples "
                    f"(applied {s_pos:+.2f} vs rejected {s_neg:+.2f}).")
    return {"active": True, "backend": be, "s_pos": s_pos, "s_neg": s_neg,
            "s_sem": s_sem, "note": note}
