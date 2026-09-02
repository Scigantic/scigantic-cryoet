"""_search.py: scoring and filters, pure functions."""
from scigantic_cryoet._search import expand_query, match_score, passes_filters


def test_expand_query_tokenizes():
    assert expand_query("SARS-CoV-2 spike") == {"sars", "cov", "2", "spike"}


def test_expand_query_empty():
    assert expand_query(None) == set()
    assert expand_query("") == set()


def test_match_score_zero_when_no_overlap():
    record = {"title": "Mitochondria in mouse neuron"}
    assert match_score(record, {"spike", "sars"}) == 0.0


def test_match_score_partial_overlap():
    record = {"title": "Neuronal synapse tomography", "organism": "Homo sapiens"}
    score = match_score(record, {"neuron", "spike"})
    assert 0 < score < 1  # one of two terms hits


def test_match_score_title_bonus():
    record = {"title": "mitochondria study"}
    terms = {"mitochondria", "study"}
    with_bonus = match_score(record, terms, primary="mitochondria study")
    without_bonus = match_score(record, terms, primary=None)
    assert with_bonus > without_bonus


def test_passes_filters_organism_substring():
    record = {"organism": "Homo sapiens"}
    assert passes_filters(record, organism="sapiens")
    assert not passes_filters(record, organism="mouse")


def test_passes_filters_has_annotations():
    assert passes_filters({"n_annotations": 3}, has_annotations=True)
    assert not passes_filters({"n_annotations": 0}, has_annotations=True)
    assert passes_filters({"n_annotations": 0}, has_annotations=False)


def test_passes_filters_ctf_corrected_tri_state():
    assert passes_filters({"ctf_corrected": True}, ctf_corrected=True)
    assert not passes_filters({"ctf_corrected": None}, ctf_corrected=True)
    assert not passes_filters({"ctf_corrected": None}, ctf_corrected=False)
