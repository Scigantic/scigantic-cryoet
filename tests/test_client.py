"""catalog.py -- CryoetClient (no network, monkeypatched requests.Session.get)."""
import scigantic_cryoet as sc
from scigantic_cryoet.catalog import CryoetClient


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, content=b""):
        self._payload = payload
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_dataset_metadata(monkeypatch):
    fake = {"dataset_title": "Neuronal synapse tomography"}
    monkeypatch.setattr(sc.catalog._session, "get", lambda *a, **kw: _FakeResponse(fake))
    md = CryoetClient().dataset_metadata(10000)
    assert md["dataset_title"] == "Neuronal synapse tomography"


def test_dataset_metadata_404(monkeypatch):
    import pytest
    monkeypatch.setattr(sc.catalog._session, "get",
                         lambda *a, **kw: _FakeResponse(status_code=404))
    with pytest.raises(FileNotFoundError):
        CryoetClient().dataset_metadata(999999)


def test_runs_parses_common_prefixes(monkeypatch):
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        b'<CommonPrefixes><Prefix>10000/Images/</Prefix></CommonPrefixes>'
        b'<CommonPrefixes><Prefix>10000/TS_001/</Prefix></CommonPrefixes>'
        b'<CommonPrefixes><Prefix>10000/TS_002/</Prefix></CommonPrefixes>'
        b'</ListBucketResult>'
    )
    monkeypatch.setattr(sc.catalog._session, "get", lambda *a, **kw: _FakeResponse(content=xml))
    runs = CryoetClient().runs(10000)
    assert runs == ["TS_001", "TS_002"]  # Images/ is not a run


def test_thumbnail_and_snapshot_urls():
    c = CryoetClient()
    assert c.thumbnail_url(10000).endswith("10000/Images/thumbnail.gif")
    assert c.snapshot_url(10000).endswith("10000/Images/snapshot.gif")
