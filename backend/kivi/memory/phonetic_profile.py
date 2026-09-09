"""Accent-adaptive ("personal") phonetics.

A generic phonetic algorithm (Soundex / Metaphone / the coarse key in
``kivi.phonetics``) encodes how English *in general* sounds. It is the same for
every user. But "personal phonetic memory" is about **one particular person**: a
given speaker + microphone + ASR model mangles the same sounds the same way, over
and over. If this user's transcription always writes ``w`` where they said ``v``,
or drops a trailing ``n``, that is a fact about *them* worth learning.

This module turns the user's own corrections into a small, inspectable
**accent profile** and uses it two ways at retrieval time:

  1. **Candidate creation** - apply the learned substitutions to an unmatched
     span; if the result lands on a known memory, nominate it. This catches
     mishearings that generic phonetics + fuzzy both miss.
  2. **Disambiguation prior** - a memory this user's ASR has demonstrably
     mangled before is a more likely target for a fresh mishearing than one
     they have never had to correct.

Everything here is deterministic and stdlib-only. Rules are derived by aligning
the misheard surface with the chosen form (Levenshtein backtrace) and coalescing
each run of edits into one ``src -> dst`` chunk, tagged by word position.
"""
from __future__ import annotations

import math

from kivi.config import PP
from kivi.normalization import normalize_token
from kivi.db.store import now_iso

_MAX_CHUNK = int(PP.get("max_chunk_len", 3))


# --------------------------------------------------------------------------- #
# pure: derive rules from a (misheard -> meant) pair
# --------------------------------------------------------------------------- #

def _edit_ops(a: str, b: str) -> list[tuple[str, str, str]]:
    """Levenshtein backtrace. Ops are ('match'|'sub'|'del'|'ins', a_char, b_char).

    'del' = character present in ``a`` (ASR) but not ``b`` (meant).
    'ins' = character present in ``b`` but not ``a``.
    Deterministic tie-break: diagonal (match/sub) > up (del) > left (ins).
    """
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j - 1] + cost, dp[i - 1][j] + 1, dp[i][j - 1] + 1)

    ops: list[tuple[str, str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if a[i - 1] == b[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                ops.append(("match" if cost == 0 else "sub", a[i - 1], b[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", a[i - 1], ""))
            i -= 1
            continue
        ops.append(("ins", "", b[j - 1]))
        j -= 1
    ops.reverse()
    return ops


def derive_rules(misheard: str, meant: str) -> list[dict]:
    """Return the substitution rules explaining ``misheard`` -> ``meant``.

    Each rule: ``{"position": onset|medial|coda, "src": <chunk>, "dst": <chunk>}``
    where ``src`` is what ASR produced and ``dst`` what the user meant.
    """
    a = normalize_token(misheard)
    b = normalize_token(meant)
    if not a or not b or a == b:
        return []
    ops = _edit_ops(a, b)
    rules: list[dict] = []
    i = 0
    while i < len(ops):
        if ops[i][0] == "match":
            i += 1
            continue
        j = i
        src_chunk, dst_chunk = [], []
        while j < len(ops) and ops[j][0] != "match":
            if ops[j][1]:
                src_chunk.append(ops[j][1])
            if ops[j][2]:
                dst_chunk.append(ops[j][2])
            j += 1
        src = "".join(src_chunk)
        dst = "".join(dst_chunk)
        position = "onset" if i == 0 else ("coda" if j == len(ops) else "medial")
        # keep rules local: whole-word rewrites are noise, not an accent pattern
        if 0 < max(len(src), len(dst)) <= _MAX_CHUNK:
            rules.append({"position": position, "src": src, "dst": dst})
        i = j
    return rules


# --------------------------------------------------------------------------- #
# pure: apply the profile to a token
# --------------------------------------------------------------------------- #

def _apply_one(rule: dict, token: str) -> set[str]:
    src, dst, pos = rule["src"], rule["dst"], rule["position"]
    out: set[str] = set()
    if src == "":  # insertion: ASR dropped dst; try putting it back
        if pos == "onset":
            out.add(dst + token)
        elif pos == "coda":
            out.add(token + dst)
        else:
            for k in range(1, len(token)):
                out.add(token[:k] + dst + token[k:])
        return out
    start = 0
    while True:
        k = token.find(src, start)
        if k < 0:
            break
        end = k + len(src)
        at_start, at_end = (k == 0), (end == len(token))
        ok = {
            "onset": at_start,
            "coda": at_end,
            "medial": not at_start and not at_end,
        }.get(pos, True)
        if ok:
            out.add(token[:k] + dst + token[end:])
        start = k + 1
    return out


def weight_for(observations: int) -> float:
    k = float(PP.get("weight_k", 2.5))
    cap = float(PP.get("weight_cap", 1.0))
    return round(min(cap, 1.0 - math.exp(-max(0, observations) / k)), 4)


def apply_profile(rules: list[dict], token: str, *, max_rules: int = 2, cap: int = 64) -> set[str]:
    """All strings reachable from ``token`` by applying up to ``max_rules`` rules."""
    token = normalize_token(token)
    if not token or not rules:
        return set()
    seen = {token}
    frontier = {token}
    for _ in range(max_rules):
        nxt: set[str] = set()
        for t in frontier:
            for r in rules:
                for v in _apply_one(r, t):
                    if v and v not in seen:
                        seen.add(v)
                        nxt.add(v)
                        if len(seen) > cap:
                            return seen - {token}
        frontier = nxt
        if not frontier:
            break
    return seen - {token}


def rule_label(rule: dict) -> str:
    return f"{rule['src'] or '(nil)'}->{rule['dst'] or '(nil)'} ({rule['position']})"


# --------------------------------------------------------------------------- #
# db: the profile lives in one inspectable table
# --------------------------------------------------------------------------- #

def record_pair(conn, misheard: str, meant: str, *, origin: str = "learned") -> list[str]:
    """Fold one (misheard -> meant) correction into the accent profile."""
    ts = now_iso()
    labels: list[str] = []
    for r in derive_rules(misheard, meant):
        row = conn.execute(
            "SELECT * FROM sound_pattern WHERE position = ? AND src = ? AND dst = ?",
            (r["position"], r["src"], r["dst"]),
        ).fetchone()
        if row:
            obs = row["observations"] + 1
            conn.execute(
                "UPDATE sound_pattern SET observations = ?, weight = ?, last_seen = ? WHERE id = ?",
                (obs, weight_for(obs), ts, row["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO sound_pattern (position, src, dst, observations, weight,
                                              origin, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (r["position"], r["src"], r["dst"], 1, weight_for(1), origin, ts, ts),
            )
        labels.append(rule_label(r))
    return labels


def load_profile(conn, *, active_only: bool = True) -> list[dict]:
    q = "SELECT * FROM sound_pattern"
    args: tuple = ()
    if active_only:
        q += " WHERE observations >= ?"
        args = (int(PP.get("min_observations", 2)),)
    q += " ORDER BY weight DESC, observations DESC, id ASC"
    return [dict(r) for r in conn.execute(q, args).fetchall()]


def profile_weight_index(profile: list[dict]) -> dict[tuple[str, str, str], float]:
    return {(r["position"], r["src"], r["dst"]): r["weight"] for r in profile}


def asr_error_prior(conn, memory_id: int) -> tuple[float, int]:
    """(prior in [0,1], raw count) - how often THIS user's ASR has mangled this memory.

    Counts positive observations whose recorded surface differs from the chosen form,
    i.e. a genuine mishearing the user had to fix - not a plain teach.
    """
    n = conn.execute(
        """SELECT COUNT(*) AS c FROM observation
           WHERE memory_id = ?
             AND type IN ('asr_pair', 'explicit_correction', 'confirmation')
             AND target_span IS NOT NULL AND TRIM(target_span) <> ''
             AND LOWER(REPLACE(target_span, ' ', '')) <> LOWER(REPLACE(COALESCE(chosen_form, ''), ' ', ''))""",
        (memory_id,),
    ).fetchone()["c"]
    k = float(PP.get("prior_k", 3.0))
    return round(1.0 - math.exp(-n / k), 4), n
