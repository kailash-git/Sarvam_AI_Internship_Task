from app.services.phonetics import (
    ngram_spans,
    phonetic_similarity,
    surface_similarity,
    tokenize,
)


def test_identical_after_normalisation_is_one():
    assert phonetic_similarity("Kivi", "kivi") == 1.0
    assert phonetic_similarity("post gres", "Postgres") == 1.0


def test_close_homophones_score_high():
    assert phonetic_similarity("kiwi", "Kivi") >= 0.9
    assert phonetic_similarity("Aditya", "Aaditya") >= 0.9
    assert phonetic_similarity("pie torch", "PyTorch") >= 0.9


def test_unrelated_words_score_low():
    assert phonetic_similarity("kiwi", "call") < 0.55
    assert phonetic_similarity("review", "revenue") < 0.7


def test_surface_similarity_ignores_metaphone_and_prefix_bonus():
    # metaphone collapses these but the spellings are far apart
    assert surface_similarity("Colin", "Cologne") < 0.85
    assert surface_similarity("Terra", "Tara") < 0.85
    # casing-only / semivowel swap stays close
    assert surface_similarity("kivi", "Kivi") == 1.0
    assert surface_similarity("kiwi", "Kivi") >= 0.85


def test_ngram_spans_longest_first():
    spans = ngram_spans(tokenize("a b c"), max_n=3)
    assert spans[0] == (0, 3)
    assert (0, 1) in spans and (2, 3) in spans
