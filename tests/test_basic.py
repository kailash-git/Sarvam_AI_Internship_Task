"""Prototype test suite (stdlib unittest - no pytest needed).

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from kivi.phonetics import phonetic_key           # noqa: E402
from kivi.textmatch import ratio                   # noqa: E402
from kivi.normalization import content_tokens      # noqa: E402
from kivi.db.reset import reset                    # noqa: E402
from kivi.db.store import connect, get_memory_by_norm, table_counts  # noqa: E402
from kivi.normalization import normalize_token     # noqa: E402
from kivi.memory.learning import observe           # noqa: E402
from kivi.memory.phonetic_profile import derive_rules, apply_profile, load_profile  # noqa: E402
from kivi.pipeline import process                  # noqa: E402


class Phonetics(unittest.TestCase):
    def test_asr_confusions_collide(self):
        for w in ("kiwi", "kivy", "civi"):
            self.assertEqual(phonetic_key(w), phonetic_key("kivi"))

    def test_unrelated_word_is_not_a_candidate(self):
        # the lightweight phonetic key is coarse (coffee/kivi can share a key),
        # so retrieval also enforces a fuzzy floor - the invariant that matters
        # is that an unrelated word never becomes a candidate.
        reset()
        conn = connect()
        try:
            from kivi.memory.retrieval import find_candidates
            self.assertEqual(find_candidates(conn, "coffee"), [])
            self.assertTrue(any(c.canonical == "Kivi" for c in find_candidates(conn, "kiwi")))
        finally:
            conn.close()

    def test_fuzzy_ratio_bounds(self):
        self.assertEqual(ratio("kivi", "kivi"), 1.0)
        self.assertLess(ratio("kivi", "elephant"), 0.4)


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset()

    def _mem(self, text):
        return process(text=text, persist=False)["memory_aware_text"]

    def _action(self, text, span):
        r = process(text=text, persist=False)
        for d in r["decisions"]:
            if normalize_token(d["span"]) == normalize_token(span):
                return d["action"]
        return "KEEP"

    def test_software_context_replaces(self):
        self.assertEqual(self._mem("open the kiwi service"), "Open the Kivi service.")
        self.assertEqual(self._action("open the kiwi service", "kiwi"), "REPLACE")

    def test_fruit_context_is_deliberate_keep(self):
        self.assertEqual(self._mem("I ate a kiwi today"), "I ate a kiwi today.")
        self.assertEqual(self._action("I ate a kiwi today", "kiwi"), "KEEP")

    def test_ambiguous_surface_defers(self):
        self.assertEqual(self._action("ask civi", "civi"), "DEFER")

    def test_proposed_memory_never_auto_replaces(self):
        self.assertIn(self._action("we should ship devy this sprint", "devy"), ("DEFER", "KEEP"))

    def test_unknown_word_is_kept(self):
        self.assertEqual(self._mem("deploy the zephyr module"), "Deploy the zephyr module.")

    def test_processing_does_not_mutate_memory(self):
        conn = connect()
        try:
            before = get_memory_by_norm(conn, "kivi")["confidence"]
        finally:
            conn.close()
        for _ in range(3):
            process(text="open the kiwi service", persist=False)
        conn = connect()
        try:
            after = get_memory_by_norm(conn, "kivi")["confidence"]
        finally:
            conn.close()
        self.assertEqual(before, after)


class Learning(unittest.TestCase):
    def setUp(self):
        reset()

    def test_scoped_rejection_does_not_touch_global_confidence(self):
        conn = connect()
        try:
            before = get_memory_by_norm(conn, "kivi")["confidence"]
        finally:
            conn.close()
        res = observe(type="rejection", rejected_form="Kivi", chosen_form="kiwi",
                      context={"keywords": ["planted", "vine"], "domain": "general"})
        self.assertEqual(res["before"]["confidence"], res["after"]["confidence"])
        self.assertEqual(res["after"]["confidence"], before)

    def test_scoped_rejection_blocks_that_context_only(self):
        observe(type="rejection", rejected_form="Kivi", chosen_form="kiwi",
                context={"keywords": ["planted", "vine", "garden"], "domain": "general"})
        r1 = process(text="I planted a kiwi vine in the garden", persist=False)
        r2 = process(text="deploy kiwi to staging", persist=False)
        self.assertEqual(r1["memory_aware_text"], "I planted a kiwi vine in the garden.")
        self.assertEqual(r2["memory_aware_text"], "Deploy Kivi to staging.")

    def test_explicit_correction_creates_memory_and_next_utterance_replaces(self):
        observe(type="explicit_correction", chosen_form="Nimbus", rejected_form="nimbers",
                context={"keywords": ["restart", "server"], "domain": "software"})
        out = process(text="restart the nimbers server", persist=False)["memory_aware_text"]
        self.assertEqual(out, "Restart the Nimbus server.")

    def test_rejection_without_existing_memory_raises(self):
        with self.assertRaises(ValueError):
            observe(type="rejection", rejected_form="Nonexistent", chosen_form="whatever")


class PersonalPhonetics(unittest.TestCase):
    """Accent-adaptive phonetics: Kivi learns HOW this user's ASR mangles sounds."""

    def setUp(self):
        reset()

    def test_derive_rules_are_position_tagged_substitutions(self):
        self.assertEqual(derive_rules("kiwi", "kivi"),
                         [{"position": "medial", "src": "w", "dst": "v"}])
        onset = derive_rules("lehaan", "rehan")
        self.assertIn({"position": "onset", "src": "l", "dst": "r"}, onset)
        self.assertEqual(derive_rules("arju", "arjun"),
                         [{"position": "coda", "src": "", "dst": "n"}])
        self.assertEqual(derive_rules("same", "same"), [])

    def test_apply_profile_is_bounded_and_directional(self):
        rules = [{"position": "onset", "src": "l", "dst": "r"}]
        self.assertIn("rehan", apply_profile(rules, "lehan"))
        self.assertNotIn("lehan", apply_profile(rules, "rehan"))  # l->r, not r->l

    def test_accent_rule_nominates_a_never_seen_mishearing(self):
        # generic phonetics + fuzzy both miss "lehan" -> "Rehan" (cross-class l/r)
        for wrong in ("lehaan", "lehin"):
            observe(type="explicit_correction", chosen_form="Rehan", rejected_form=wrong,
                    context={"keywords": ["tell", "sync", "review"], "domain": "people"})
        r = process(text="tell lehan about the sync", persist=False)
        self.assertEqual(r["memory_aware_text"], "Tell Rehan about the sync.")
        dec = next(d for d in r["decisions"] if normalize_token(d["span"]) == "lehan")
        self.assertEqual(dec["action"], "REPLACE")
        self.assertTrue(dec["personal"]["method_personal"])

    def test_history_lifts_a_borderline_match(self):
        # same input as multi-01 (which DEFERs); prior Sivi mishearings -> REPLACE
        for wrong in ("sivvy", "siviee", "seavey"):
            observe(type="explicit_correction", chosen_form="Sivi", rejected_form=wrong,
                    context={"keywords": ["told", "meeting", "review"], "domain": "people"})
        r = process(text="open kiwi and tell sibi", persist=False)
        self.assertEqual(r["memory_aware_text"], "Open Kivi and tell Sivi.")

    def test_accent_profile_never_overrides_deliberate_keep(self):
        for wrong in ("kivee", "kiwie"):
            observe(type="explicit_correction", chosen_form="Kivi", rejected_form=wrong,
                    context={"keywords": ["deploy", "service"], "domain": "software"})
        before = process(text="the kiwi was ripe and sweet", persist=False)
        self.assertEqual(before["memory_aware_text"], "The kiwi was ripe and sweet.")
        conn = connect()
        try:
            self.assertGreaterEqual(load_profile(conn).__len__(), 1)  # profile is active
        finally:
            conn.close()

    def test_processing_does_not_grow_the_accent_profile(self):
        conn = connect()
        try:
            before = table_counts(conn)["sound_pattern"]
        finally:
            conn.close()
        for _ in range(3):
            process(text="open the kiwi service", persist=False)
        conn = connect()
        try:
            self.assertEqual(table_counts(conn)["sound_pattern"], before)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
