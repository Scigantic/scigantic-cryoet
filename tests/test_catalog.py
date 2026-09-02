"""catalog.py: CryoetCatalog (no network)."""
import sys
import types

import pandas as pd
import pytest

import scigantic_cryoet as sc
from scigantic_cryoet.catalog import _as_list, _empiar_acc


def _catalog():
    cat = sc.CryoetCatalog()
    cat._df = pd.DataFrame([
        {"id": 10000, "title": "Neuronal synapse tomography", "organism": "Homo sapiens",
         "sample_type": "cell", "disease": None, "n_runs": 3, "emdb_ids": ["EMD-1234"],
         "empiar_ids": [], "n_annotations": 2, "ctf_corrected": True},
        {"id": 10301, "title": "SARS-CoV-2 spike in situ", "organism": "SARS-CoV-2",
         "sample_type": "organelle", "disease": "COVID-19", "n_runs": 1, "emdb_ids": [],
         "empiar_ids": ["11123"], "n_annotations": 0, "ctf_corrected": None},
        {"id": 10450, "title": "Mitochondria in mouse neuron", "organism": "Mus musculus",
         "sample_type": "organelle", "disease": None, "n_runs": 5, "emdb_ids": [],
         "empiar_ids": [], "n_annotations": 4, "ctf_corrected": False},
    ])
    cat._meta = {"catalog_entries": 3}
    return cat


def test_search_by_query_matches_title_and_organism():
    hits = _catalog().search("neuron")
    assert set(hits["id"]) == {10000, 10450}


def test_search_by_organism_filter():
    hits = _catalog().search(organism="Mus musculus")
    assert list(hits["id"]) == [10450]


def test_search_has_emdb():
    hits = _catalog().search(has_emdb=True)
    assert list(hits["id"]) == [10000]


def test_search_has_annotations_false():
    hits = _catalog().search(has_annotations=False)
    assert list(hits["id"]) == [10301]


def test_search_ctf_corrected():
    hits = _catalog().search(ctf_corrected=False)
    assert list(hits["id"]) == [10450]


def test_search_sort_runs():
    hits = _catalog().search(sort="runs")
    assert list(hits["id"]) == [10450, 10000, 10301]


def test_search_limit():
    assert len(_catalog().search(limit=1)) == 1


def test_search_no_query_returns_all():
    assert len(_catalog().search()) == 3


def test_catalog_meta_passthrough():
    assert _catalog().catalog_meta == {"catalog_entries": 3}


def test_load_local_path(tmp_path):
    import json
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({
        "meta": {"catalog_entries": 1},
        "entries": [{"id": 1, "title": "x"}],
    }))
    cat = sc.CryoetCatalog(url=str(p))
    df = cat.load()
    assert list(df["id"]) == [1]
    assert cat.catalog_meta == {"catalog_entries": 1}


def test_load_raises_on_wrong_shape(tmp_path):
    """The exact bug this test guards against shipped in v0.1.0 development:
    an earlier version of load() looked for a 'datasets' key that the real
    builder (cryoet_build_catalog.py) never writes (it writes 'entries'),
    and silently fell back to an empty-but-still-queryable catalog instead
    of raising. Caught by smoke-testing against a real catalog file, not by
    a unit test; this test exists so it can't regress silently again."""
    import json
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({"meta": {}, "datasets": [{"id": 1}]}))
    with pytest.raises(ValueError, match="entries"):
        sc.CryoetCatalog(url=str(p)).load()


def test_load_http_raises_on_failure(monkeypatch):
    """A failed fetch must raise, not silently return an empty/degraded
    catalog, the exact failure mode scigantic-empiar's load() was fixed
    to stop making (see its own test_catalog_load_raises_instead_of_degrading)."""
    import requests

    def _boom(*a, **kw):
        raise requests.exceptions.ConnectionError("unreachable")

    monkeypatch.setattr(sc.catalog._session, "get", _boom)
    with pytest.raises(requests.exceptions.ConnectionError):
        sc.CryoetCatalog().load()


def test_as_list_nan_safe():
    assert _as_list(None) == []
    assert _as_list(float("nan")) == []
    assert _as_list("EMD-1234") == ["EMD-1234"]
    assert _as_list(["EMD-1", "EMD-2"]) == ["EMD-1", "EMD-2"]


def test_empiar_acc_normalises():
    assert _empiar_acc("EMPIAR-10988") == "10988"
    assert _empiar_acc("10988") == "10988"
    assert _empiar_acc("010988") == "10988"


def _fake_emdb_module():
    class _FakeEmdbCatalog:
        def load(self):
            return pd.DataFrame([
                {"id": "EMD-1234", "title": "Some structure", "resolution_a": 3.2},
                {"id": "EMD-5678", "title": "Unrelated structure", "resolution_a": 4.1},
            ])
    return types.SimpleNamespace(EmdbCatalog=_FakeEmdbCatalog, acc=lambda x: str(x).upper())


def _fake_empiar_module():
    class _FakeEmpiarCatalog:
        def load(self):
            return pd.DataFrame([
                {"id": "11123", "size_gb": 12.5, "method": "tomography"},
            ])
    return types.SimpleNamespace(EmpiarCatalog=_FakeEmpiarCatalog)


def test_with_emdb_joins(monkeypatch):
    monkeypatch.setitem(sys.modules, "scigantic_emdb", _fake_emdb_module())
    out = _catalog().with_emdb()
    assert list(out["cryoet_id"]) == [10000]
    assert out.iloc[0]["emdb_id"] == "EMD-1234"
    assert out.iloc[0]["resolution_a"] == 3.2


def test_with_emdb_no_matches_is_empty(monkeypatch):
    monkeypatch.setitem(sys.modules, "scigantic_emdb", _fake_emdb_module())
    cat = _catalog()
    cat._df = cat._df[cat._df["id"] != 10000]  # drop the only row with an emdb_id
    assert cat.with_emdb().empty


def test_with_emdb_unavailable_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "scigantic_emdb", None)
    with pytest.raises(RuntimeError, match="scigantic_emdb"):
        _catalog().with_emdb()


def test_with_empiar_joins(monkeypatch):
    monkeypatch.setitem(sys.modules, "scigantic_empiar", _fake_empiar_module())
    out = _catalog().with_empiar()
    assert list(out["cryoet_id"]) == [10301]
    assert out.iloc[0]["empiar_id"] == "11123"
    assert out.iloc[0]["raw_method"] == "tomography"


def test_with_empiar_unavailable_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "scigantic_empiar", None)
    with pytest.raises(RuntimeError, match="scigantic_empiar"):
        _catalog().with_empiar()
