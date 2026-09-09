import pytest

from app.services import learning
from app.services.pipeline import _decide, process
from app.services.retrieval import Candidate


def _seed_brief():
    learning.learn_from_correction(asr_text="tell aditya", formatted_text="Tell Aditya.",
                                   corrected_text="Tell Aaditya.", category="person")
    learning.learn_from_correction(asr_text="ask aditya", formatted_text="Ask Aditya.",
                                   corrected_text="Ask Aaditya.", category="person")
    learning.learn_from_dictionary(canonical="Kivi", category="product", aliases=["kiwi"])
    learning.learn_from_dictionary(canonical="Sarvam", category="org", aliases=["servam"])


def test_brief_example_end_to_end():
    _seed_brief()
    r = process("ask aditya to review the sarvam kiwi service",
                "Ask Aditya to review the Sarvam Kiwi service.", persist=False)
    assert r.memory_aware_text == "Ask Aaditya to review the Sarvam Kivi service."
    assert r.intervened is True
    applied = {d.canonical for d in r.decisions if d.action == "apply"}
    assert applied == {"Aaditya", "Kivi"}


def test_food_context_blocks_product_homophone():
    learning.learn_from_dictionary(canonical="Kivi", category="product", aliases=["kiwi"])
    r = process("i ate a kiwi for breakfast", "I ate a kiwi for breakfast.", persist=False)
    assert r.intervened is False
    assert any(d.reason_tag == "food_context_guard" for d in r.decisions)


def test_candidate_is_not_applied():
    learning.learn_from_correction(formatted_text="Send it to Nikhil.",
                                   corrected_text="Send it to Nikhhil.", category="person")
    r = process("loop in nikhil", "Loop in Nikhil.", persist=False)
    assert r.intervened is False
    assert any(d.reason_tag == "not_active" for d in r.decisions)


def test_ambiguous_names_do_nothing():
    learning.learn_from_dictionary(canonical="Jon", category="person")
    learning.learn_from_dictionary(canonical="John", category="person")
    r = process("ask jhon to sign", "Ask Jhon to sign.", persist=False)
    assert r.intervened is False
    assert any(d.reason_tag == "ambiguous_conflict" for d in r.decisions)


def test_context_resolves_ambiguity():
    learning.learn_from_dictionary(canonical="Jon", category="person")
    learning.learn_from_dictionary(canonical="John", category="person")
    r = process("remind jon then tell jhon", "Remind Jon then tell Jhon.", persist=False)
    assert r.memory_aware_text == "Remind Jon then tell Jon."


def test_threshold_gates_a_weak_combined_score():
    """A candidate whose combined score sits just under the default threshold
    (0.72) is skipped with `below_threshold` — not applied, not mislabelled."""
    from app.services.pipeline import settings

    c = Candidate(
        entry_id=1, canonical="Zephyr", category="term", status="active",
        confidence=0.55, span_text="Zephyra", start=0, end=7,
        matched_form="zephira", matched_via="alias",
        phonetic_score=0.70, combined_score=settings.apply_threshold - 0.01,
        span_is_common_word=False, already_canonical=False,
        context_tokens=["the", "build"], rivals=[],
    )
    d = _decide(c)
    assert d.action == "skip"
    assert d.reason_tag == "below_threshold"

    c_ok = Candidate(**{**c.__dict__, "combined_score": settings.apply_threshold + 0.01})
    assert _decide(c_ok).action == "apply"


def test_persisted_run_records_utterance_and_interventions():
    _seed_brief()
    from app.services import repo

    r = process("ask aditya about kiwi", "Ask Aditya about Kiwi.", persist=True)
    assert r.utterance_id is not None
    utts = repo.recent_utterances(limit=1)
    assert utts[0]["memory_aware_text"] == "Ask Aaditya about Kivi."
    stats = repo.stats()
    assert stats["interventions_applied"] >= 2
