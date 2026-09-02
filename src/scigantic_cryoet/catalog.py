"""catalog.py: the searchable index, and a live per-dataset metadata client.

The CZ CryoET Data Portal (`s3://cryoet-data-portal-public`, anonymous,
~370 datasets as of 2026-09) has no search of its own: a bucket whose top
level is nothing but numeric dataset ids. `CryoetCatalog` loads a pre-built
index (one JSON file, produced by the monorepo's `cryoet_build_catalog.py`
batch job) so filtering across every dataset is instant, no live reads.
`CryoetClient` is the complementary live path, for the current state of one
dataset the snapshot might not have, or a dataset newer than the index.

This package does not read tomogram pixel data. The portal already ships
`thumbnail.gif`/`snapshot.gif` per dataset (unlike EMPIAR, which ships no
previews at all, see scigantic-empiar), and the official `cryoet-data-portal`
client already reads the OME-Zarr volumes well. Reinventing either here would
just be a second, divergent copy of something that already works.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, cast

import pandas as pd
import requests

from ._search import expand_query, match_score, passes_filters

__all__ = ["CryoetCatalog", "CryoetClient"]

BUCKET = "cryoet-data-portal-public"
ENDPOINT = f"https://{BUCKET}.s3.amazonaws.com"

# Not live yet: this points at where the monorepo's onboarding batch job will
# publish the built index, same rollout order scigantic-empiar and
# scigantic-emdb followed (library ships, then the catalog lands). Until then
# CryoetCatalog.load() 404s. Point SCIGANTIC_CRYOET_CATALOG at a local
# `cryoet_build_catalog.py --out` file to develop against real data meanwhile.
CATALOG_URL = os.environ.get(
    "SCIGANTIC_CRYOET_CATALOG",
    "https://scigantic-cryoet-catalog.s3.amazonaws.com/catalog.json",
)

_UA = {"User-Agent": "Scigantic-cryoet/0.1 (+https://scigantic.com; mailto:support@scigantic.com)"}
_session = requests.Session()
_session.headers.update(_UA)

_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def _as_list(v: Any) -> list[Any]:
    """NaN-safe list coercion for a DataFrame cell that should hold a list.

    `v or []` is wrong here: a missing cell reads back as NaN, NaN is truthy,
    and the caller then iterates a float. Returns [] for missing, wraps a bare
    scalar, and passes a real list through. Same trap and fix as
    scigantic-emdb's own `_coerce._as_list`.
    """
    if v is None or (isinstance(v, float) and v != v):
        return []
    if isinstance(v, (list, tuple, set)):
        return [x for x in v if x is not None and x == x]
    return [v]


def _empiar_acc(entry_id: Any) -> str:
    """'EMPIAR-10988' / '10988' / '010988' -> '10988', matching the bare,
    unpadded digit string `EmpiarCatalog`'s own `id` column uses."""
    s = str(entry_id).strip().upper().replace("EMPIAR-", "")
    return s.lstrip("0") or "0"


class CryoetClient:
    """Live per-dataset metadata, straight from the portal's own bucket.

    Anonymous S3 REST, no boto3, no credentials: the same shape as the
    monorepo's onboarding script. Useful for a dataset newer than whatever
    catalog snapshot is loaded, or to double-check a stale field.
    """

    def dataset_metadata(self, dataset_id: int | str) -> dict[str, Any]:
        r = _session.get(f"{ENDPOINT}/{dataset_id}/dataset_metadata.json", timeout=30)
        if r.status_code == 404:
            raise FileNotFoundError(f"no dataset_metadata.json for dataset {dataset_id}")
        r.raise_for_status()
        result: dict[str, Any] = r.json()
        return result

    def runs(self, dataset_id: int | str) -> list[str]:
        """Run directory names under a dataset (COMPLETE, one delimiter listing)."""
        q = {"list-type": "2", "prefix": f"{dataset_id}/", "delimiter": "/"}
        r = _session.get(f"{ENDPOINT}/?{urllib.parse.urlencode(q)}", timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        names = [
            cp.text.rstrip("/").split("/")[-1]
            for cp in root.findall(f"{_S3_NS}CommonPrefixes/{_S3_NS}Prefix") if cp.text
        ]
        return [n for n in names if n != "Images"]

    def thumbnail_url(self, dataset_id: int | str) -> str:
        return f"{ENDPOINT}/{dataset_id}/Images/thumbnail.gif"

    def snapshot_url(self, dataset_id: int | str) -> str:
        return f"{ENDPOINT}/{dataset_id}/Images/snapshot.gif"


class CryoetCatalog:
    """Searchable catalog across every CryoET Data Portal dataset.

    Field semantics vary by how the index was built, see the `catalog_meta`
    property before trusting a fill rate. `title`/`description`/`organism`/
    `sample_type`/`disease`/`assay`/`n_runs` etc. are COMPLETE (sourced from
    each dataset's own `dataset_metadata.json`, which every dataset has).
    `voxel_spacings`/`tomogram_size`/`reconstruction_method`/`ctf_corrected`/
    `annotation_objects` etc. describe ONE run per dataset (`sampled_run`),
    not every run: walking every run of every dataset is thousands of
    listings for detail that barely varies within a dataset. A dataset with
    heterogeneous runs will be under-reported on these fields specifically.
    """

    def __init__(self, url: str = CATALOG_URL) -> None:
        self.url = url
        self._df: pd.DataFrame | None = None
        self._meta: dict[str, Any] | None = None

    def load(self) -> pd.DataFrame:
        if self._df is not None:
            return self._df
        if self.url.startswith("http://") or self.url.startswith("https://"):
            r = _session.get(self.url, timeout=30)
            r.raise_for_status()
            payload = r.json()
        else:
            with open(self.url) as fh:
                payload = json.load(fh)
        # Raise on an unexpected shape instead of degrading to an empty (but
        # still queryable) catalog, the exact failure mode EmpiarCatalog.load()
        # was fixed to stop making, after it once fell back to a bare listing
        # on any exception and kept answering queries as if nothing were wrong.
        if not isinstance(payload, dict) or "entries" not in payload:
            got = sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            raise ValueError(
                f"catalog at {self.url!r} has no 'entries' key (got: {got}); "
                "this reader expects the {meta, entries} shape cryoet_build_catalog.py writes"
            )
        self._meta = payload.get("meta", {})
        self._df = pd.DataFrame(payload["entries"])
        return self._df

    @property
    def catalog_meta(self) -> dict[str, Any]:
        """Build-time metadata: dataset/run counts, the complete-vs-sampled
        field split, and the sentinel-normalisation counts. Read this before
        quoting a fill rate from the catalog."""
        if self._meta is None:
            self.load()
        return self._meta or {}

    def search(self, query: str | None = None, *, organism: str | None = None,
               disease: str | None = None, sample_type: str | None = None,
               tissue: str | None = None, cell_type: str | None = None,
               assay: str | None = None, reconstruction_method: str | None = None,
               has_annotations: bool | None = None, has_emdb: bool | None = None,
               has_empiar: bool | None = None, ctf_corrected: bool | None = None,
               limit: int | None = 50, sort: str = "relevance") -> pd.DataFrame:
        """Find datasets by scientific content, not just id.

        query                free text, matched across title/description/
                             organism/sample_type/disease/assay/tissue/
                             cell_type/authors.
        organism/disease/... substring filters against the COMPLETE fields.
        has_annotations      require (or exclude, False) at least one
                             annotation on the sampled run.
        has_emdb/has_empiar  require (or exclude) a cross-reference.
        ctf_corrected        True/False (sampled-run field, see catalog_meta).
        sort                 "relevance" (default), "runs", or "id".

        Returns a DataFrame.
        """
        df = self.load().copy()
        if df.empty:
            return df
        records = cast("list[dict[str, Any]]", df.to_dict("records"))
        terms = expand_query(query)
        primary = str(query or "").strip().lower() or None
        hits = [
            r for r in records
            if (not terms or match_score(r, terms, primary) > 0)
            and passes_filters(
                r, organism=organism, disease=disease, sample_type=sample_type,
                tissue=tissue, cell_type=cell_type, assay=assay,
                reconstruction_method=reconstruction_method,
                has_annotations=has_annotations, has_emdb=has_emdb,
                has_empiar=has_empiar, ctf_corrected=ctf_corrected)
        ]
        if sort == "relevance" and terms:
            hits.sort(key=lambda r: -match_score(r, terms, primary))
        elif sort == "runs":
            hits.sort(key=lambda r: -(r.get("n_runs") or 0))
        elif sort == "id":
            hits.sort(key=lambda r: (r.get("id") is None, r.get("id") or 0))

        out = pd.DataFrame(hits[:limit] if limit else hits)
        if out.empty:
            return out
        preferred = ["id", "title", "organism", "sample_type", "disease", "n_runs",
                     "reconstruction_method", "voxel_spacings", "emdb_ids", "empiar_ids",
                     "thumbnail_url"]
        cols = [c for c in preferred if c in out.columns]
        return out[cols + [c for c in out.columns if c not in cols]]

    def with_emdb(self, df: pd.DataFrame | None = None, limit: int | None = None) -> pd.DataFrame:
        """Join CryoET hits to the EMDB structures they cite.

        Needs `scigantic-emdb` installed (`pip install scigantic-cryoet[bridge]`),
        raises RuntimeError otherwise rather than returning an empty result that
        would look like "no cross-references" instead of "dependency missing".

        A dataset's own `emdb_ids` are already COMPLETE on the row (from its
        `dataset_metadata.json` cross-references), so this looks each one up
        directly in the EMDB catalog rather than building a reverse index the
        way `EmdbCatalog.with_empiar()` has to (there, the join key lives on
        the EMPIAR side, not the EMDB side).
        """
        try:
            from scigantic_emdb import EmdbCatalog, acc  # type: ignore[import-untyped]
        except Exception as exc:
            raise RuntimeError(f"scigantic_emdb unavailable: {exc}") from exc
        rows = self.search(limit=None) if df is None else df
        if rows is None or len(rows) == 0:
            return pd.DataFrame()
        if limit:
            rows = rows.head(limit)
        emdb = EmdbCatalog().load()
        if emdb.empty:
            return pd.DataFrame()
        by_id = {acc(r["id"]): r for r in emdb.to_dict("records") if r.get("id") is not None}
        out = []
        for r in rows.to_dict("records"):
            for eid in _as_list(r.get("emdb_ids")):
                src = by_id.get(acc(eid))
                if src is None:
                    continue
                out.append({
                    "cryoet_id": r.get("id"),
                    "title": r.get("title"),
                    "organism": r.get("organism"),
                    "emdb_id": src.get("id"),
                    "resolution_a": src.get("resolution_a"),
                    "emdb_title": src.get("title"),
                })
        return pd.DataFrame(out)

    def with_empiar(self, df: pd.DataFrame | None = None, limit: int | None = None) -> pd.DataFrame:
        """Join CryoET hits to the raw EMPIAR movies/micrographs behind them.

        Same shape as `with_emdb()`: needs `scigantic-empiar` installed, and
        looks the dataset's own COMPLETE `empiar_ids` up directly rather than
        building a reverse index. EMPIAR ids carry no leading zeros and no
        `EMPIAR-` prefix in `EmpiarCatalog`, unlike the portal's own
        cross-reference strings (`EMPIAR-10988`), so both sides are
        normalised the same way before matching.
        """
        try:
            from scigantic_empiar import EmpiarCatalog  # type: ignore[import-untyped]
        except Exception as exc:
            raise RuntimeError(f"scigantic_empiar unavailable: {exc}") from exc
        rows = self.search(limit=None) if df is None else df
        if rows is None or len(rows) == 0:
            return pd.DataFrame()
        if limit:
            rows = rows.head(limit)
        emp = EmpiarCatalog().load()
        if emp.empty:
            return pd.DataFrame()
        by_id = {_empiar_acc(r["id"]): r for r in emp.to_dict("records") if r.get("id") is not None}
        out = []
        for r in rows.to_dict("records"):
            for eid in _as_list(r.get("empiar_ids")):
                src = by_id.get(_empiar_acc(eid))
                if src is None:
                    continue
                out.append({
                    "cryoet_id": r.get("id"),
                    "title": r.get("title"),
                    "organism": r.get("organism"),
                    "empiar_id": src.get("id"),
                    "raw_size_gb": src.get("size_gb"),
                    "raw_method": src.get("method"),
                })
        return pd.DataFrame(out)

    def gallery(self, df: pd.DataFrame | None = None, cols: int = 4) -> Any:
        """HTML gallery using the portal's own thumbnail.gif per dataset."""
        from IPython.display import HTML
        import html as _html
        df = self.load() if df is None else df
        cells = []
        for _, r in df.iterrows():
            def g(key: str, default: Any = "") -> Any:
                v = r.get(key, default)
                return default if v is None or v != v else v

            did, thumb = g("id"), g("thumbnail_url")
            if thumb:
                art = (f'<img src="{_html.escape(str(thumb))}" title="dataset thumbnail"'
                       ' style="width:100%;border-radius:6px;background:#111">')
            else:
                art = ('<div style="height:120px;border-radius:6px;background:#f2f2f2;'
                       'display:flex;align-items:center;justify-content:center;color:#aaa;'
                       'font:10px sans-serif">no thumbnail</div>')
            label = str(g("title"))
            bits = [str(x) for x in (g("organism"), g("sample_type")) if x]
            if g("n_runs"):
                bits.append(f"{g('n_runs')} run(s)")
            cells.append(
                f'<div style="width:{100 // cols - 2}%;display:inline-block;vertical-align:top;'
                f'margin:1%;font:11px sans-serif">{art}'
                f'<b>CryoET-{_html.escape(str(did))}</b><br>{_html.escape(label[:70])}'
                f'<br><span style="color:#888">{" &middot; ".join(bits)}</span></div>')
        return HTML("<div>" + "".join(cells) + "</div>")  # type: ignore[no-untyped-call]
