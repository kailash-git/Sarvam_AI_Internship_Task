"""Reproducible seed data.

Everything is taught through the real learning API, so the seeded memory has
genuine provenance (observations, promotions) and the demo opens on a state that
already shows every status: active, candidate, and suppressed, plus a deliberate
phonetic ambiguity.

    python -m app.db.seed
"""
from __future__ import annotations

from app.db.migrate import migrate
from app.services import learning, repo

# (asr, formatted, corrected, category) tuples applied in order.
_CORRECTIONS = [
    # Aaditya: two corrections -> promoted to active.
    ("tell aditya about the release",
     "Tell Aditya about the release.",
     "Tell Aaditya about the release.", "person"),
    ("did aditya reply",
     "Did Aditya reply?",
     "Did Aaditya reply?", "person"),
    # PyTorch: two corrections from the ASR-mangled form -> active.
    ("we are migrating the model to pie torch",
     "We are migrating the model to Pie Torch.",
     "We are migrating the model to PyTorch.", "term"),
    ("the pie torch training loop is slow",
     "The Pie Torch training loop is slow.",
     "The PyTorch training loop is slow.", "term"),
    # Nikhhil: a single correction -> stays a candidate (not enough evidence).
    ("send it to nikhil",
     "Send it to Nikhil.",
     "Send it to Nikhhil.", "person"),
    # Jayne: one correction, then rejected twice below -> suppressed.
    ("jane will join",
     "Jane will join.",
     "Jayne will join.", "person"),
]

_DICTIONARY = [
    dict(canonical="Kivi", category="product",
         aliases=["kiwi", "kiwwi", "kivvy"], note="Sarvam's dictation product."),
    dict(canonical="Sarvam", category="org", aliases=["sarwam", "servam"],
         note="The company."),
    dict(canonical="Postgres", category="term", aliases=["post gres", "postgress"],
         note="Database; user prefers 'Postgres' over 'PostgreSQL'."),
    # Deliberate ambiguity: two real people the user knows.
    dict(canonical="Jon", category="person", aliases=[], note="Jon from design."),
    dict(canonical="John", category="person", aliases=[], note="John from finance."),
]


def seed() -> dict:
    migrate()
    for asr, formatted, corrected, category in _CORRECTIONS:
        learning.learn_from_correction(
            asr_text=asr, formatted_text=formatted,
            corrected_text=corrected, category=category,
        )
    for spec in _DICTIONARY:
        learning.learn_from_dictionary(**spec)

    # Suppress "Jayne" via two rejections.
    jayne = repo.find_entry("Jayne", "person")
    if jayne:
        learning.learn_from_rejection(entry_id=jayne["id"], note="user kept 'Jane'")
        learning.learn_from_rejection(entry_id=jayne["id"], note="user kept 'Jane' again")

    return repo.stats()


if __name__ == "__main__":
    import json

    print(json.dumps(seed(), indent=2))
