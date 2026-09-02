"""Free-text scoring over a catalog record.

Deliberately simple for v0.1: case-insensitive token overlap across the
fields a structural biologist actually searches on, no synonym expansion.
scigantic-empiar's `expand_query`/`match_score` (alias tables for "GPCR",
"cryoET", etc.) is the natural next step once this catalog has real query
traffic to tune against -- guessing synonyms ahead of usage risks the same
trap the search team has hit before: an untested expansion can silently
hurt ranking as easily as help it.
"""
from __future__ import annotations

from typing import Any

TEXT_FIELDS = (
    "title", "description", "organism", "sample_type", "disease",
    "assay", "tissue", "cell_type", "cell_strain", "cell_component",
    "reconstruction_method",
)


def _tokens(s: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in s.lower()).split() if t}


def expand_query(query: Any) -> set[str]:
    return _tokens(str(query)) if query else set()


def _record_text(record: dict[str, Any]) -> str:
    parts = []
    for f in TEXT_FIELDS:
        v = record.get(f)
        if v:
            parts.append(str(v))
    authors = record.get("authors") or []
    parts.extend(str(a) for a in authors)
    return " ".join(parts)


def match_score(record: dict[str, Any], terms: set[str], primary: str | None = None) -> float:
    """Fraction of query terms present as a SUBSTRING of some token, +1 bonus
    if the literal phrase matches the title.

    Substring, not exact token equality: "neuron" has to match "Neuronal
    synapse tomography" (the everyday case of a plain word-form mismatch,
    not literal token identity), and a catalog record with no query
    expansion yet (see the module docstring) needs whatever help substring
    matching can give it.
    """
    if not terms:
        return 1.0
    text = _record_text(record).lower()
    text_tokens = _tokens(text)
    hits = sum(1 for t in terms if any(t in tok for tok in text_tokens))
    if hits == 0:
        return 0.0
    score = hits / len(terms)
    if primary and primary in str(record.get("title") or "").lower():
        score += 1.0
    return score


def passes_filters(record: dict[str, Any], *, organism: str | None = None,
                    disease: str | None = None, sample_type: str | None = None,
                    tissue: str | None = None, cell_type: str | None = None,
                    assay: str | None = None, reconstruction_method: str | None = None,
                    has_annotations: bool | None = None, has_emdb: bool | None = None,
                    has_empiar: bool | None = None,
                    ctf_corrected: bool | None = None) -> bool:
    def _contains(field: str, needle: str | None) -> bool:
        if needle is None:
            return True
        v = record.get(field)
        return bool(v) and str(needle).lower() in str(v).lower()

    if not _contains("organism", organism):
        return False
    if not _contains("disease", disease):
        return False
    if not _contains("sample_type", sample_type):
        return False
    if not _contains("tissue", tissue):
        return False
    if not _contains("cell_type", cell_type):
        return False
    if not _contains("assay", assay):
        return False
    if not _contains("reconstruction_method", reconstruction_method):
        return False
    if has_annotations is not None:
        n = record.get("n_annotations") or 0
        if bool(n) != bool(has_annotations):
            return False
    if has_emdb is not None:
        if bool(record.get("emdb_ids")) != bool(has_emdb):
            return False
    if has_empiar is not None:
        if bool(record.get("empiar_ids")) != bool(has_empiar):
            return False
    if ctf_corrected is not None:
        if record.get("ctf_corrected") != ctf_corrected:
            return False
    return True
