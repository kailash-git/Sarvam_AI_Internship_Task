from app.services import learning, repo


def test_correction_creates_candidate_then_promotes():
    r1 = learning.learn_from_correction(
        asr_text="tell aditya", formatted_text="Tell Aditya.",
        corrected_text="Tell Aaditya.", category="person",
    )
    assert r1.changes[0].status == "candidate"
    entry_id = r1.changes[0].entry_id

    r2 = learning.learn_from_correction(
        asr_text="ask aditya", formatted_text="Ask Aditya.",
        corrected_text="Ask Aaditya.", category="person",
    )
    assert r2.changes[0].status == "active"
    assert r2.changes[0].promoted is True
    assert r2.changes[0].entry_id == entry_id


def test_dictionary_is_active_immediately_with_aliases():
    r = learning.learn_from_dictionary(
        canonical="Kivi", category="product", aliases=["kiwi", "kiwwi"],
    )
    assert r.changes[0].status == "active"
    entry = repo.get_entry(r.changes[0].entry_id)
    forms = {a["surface_form"] for a in entry["aliases"]}
    assert {"kiwi", "kiwwi"} <= forms


def test_two_rejections_suppress_an_entry():
    learning.learn_from_dictionary(canonical="Jayne", category="person")
    eid = repo.find_entry("Jayne", "person")["id"]

    learning.learn_from_rejection(entry_id=eid)
    assert repo.get_entry(eid)["status"] == "active"

    learning.learn_from_rejection(entry_id=eid)
    assert repo.get_entry(eid)["status"] == "suppressed"


def test_diff_pairs_extracts_only_changed_regions():
    pairs = learning.diff_pairs("Ask Aditya to review the Kiwi service.",
                                "Ask Aaditya to review the Kivi service.")
    assert ("Aditya", "Aaditya") in pairs
    assert ("Kiwi", "Kivi") in pairs
    assert len(pairs) == 2
