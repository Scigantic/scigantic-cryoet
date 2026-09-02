<h1 align="center">scigantic-cryoet</h1>

<p align="center">
    <a href="https://github.com/Scigantic/scigantic-cryoet/actions/workflows/ci.yml">
        <img alt="CI" src="https://github.com/Scigantic/scigantic-cryoet/actions/workflows/ci.yml/badge.svg" /></a>
    <a href="https://pypi.org/project/scigantic-cryoet/">
        <img alt="PyPI" src="https://img.shields.io/pypi/v/scigantic-cryoet" /></a>
    <a href="https://pypi.org/project/scigantic-cryoet/">
        <img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/scigantic-cryoet" /></a>
    <a href="https://github.com/Scigantic/scigantic-cryoet/blob/main/LICENSE">
        <img alt="License" src="https://img.shields.io/github/license/Scigantic/scigantic-cryoet" /></a>
</p>

Search the [CZ CryoET Data Portal](https://cryoetdataportal.czscience.com/) from Python.

```python
import scigantic_cryoet as cryoet

cat = cryoet.CryoetCatalog()
cat.search("Legionella", has_annotations=True)
```

## Installation

```console
$ pip install scigantic-cryoet
```

## Why this exists

`s3://cryoet-data-portal-public` is public and anonymous, but its top level is nothing but numeric dataset ids. There is no search: finding "a tomogram of a ribosome in a mammalian neuron" otherwise means opening `dataset_metadata.json` by hand, once per dataset, across all ~370 of them. This package is a catalog and search layer on top of that bucket, the same move [`scigantic-empiar`](https://github.com/Scigantic/scigantic-empiar) and [`scigantic-emdb`](https://github.com/Scigantic/scigantic-emdb) made for their own archives.

It does not read tomogram pixel data or reimplement OME-Zarr access. The portal already ships a `thumbnail.gif`/`snapshot.gif` per dataset (unlike EMPIAR, which ships no previews at all), and the official [`cryoet-data-portal`](https://pypi.org/project/cryoet-data-portal/) client already reads the zarr volumes well. This package's job ends at "which dataset, and where."

## The catalog

`CryoetCatalog` loads a pre-built index so search/filter across every dataset is instant, no live reads. Measured against the full portal, 2026-09-02 (370/370 datasets, 0 failures, 129s to build):

| field | fill rate | scope |
|---|---:|---|
| title, description, organism, sample_type, disease, assay | 100% | every dataset |
| n_runs, authors, release/deposition dates | 100% | every dataset |
| organism (named), tissue, cell_type | 97% / 96% / 94% | every dataset |
| voxel_spacings, reconstruction_method, annotation_objects | 98% / 98% / 92% | **one run per dataset** |
| emdb_ids / empiar_ids present | 12% / 6.5% | cross-reference, when deposited |

**Read `catalog_meta` before trusting a fill rate.** Fields drawn from `dataset_metadata.json` (title, organism, sample_type, disease, assay, cross-references, ...) are COMPLETE: every dataset has one. Fields that live one level down at the run/tomogram level (`voxel_spacings`, `reconstruction_method`, `ctf_corrected`, `annotation_objects`, ...) describe **one run**, named in `sampled_run`: walking every run of every dataset is thousands of listings for detail that barely varies within a dataset. `catalog_meta` names exactly which fields are sampled, so this can't be missed the way an earlier internal EMPIAR catalog once advertised "all ~3,000 entries" while actually holding 12.

```python
cat = cryoet.CryoetCatalog()
cat.catalog_meta        # {"catalog_entries": 370, "sampled_fields": [...], ...}

cat.search(organism="Homo sapiens", has_annotations=True, sort="runs")
cat.search(has_emdb=True, sort="runs")   # datasets cross-referenced to EMDB, most runs first
cat.gallery(cat.search("spike"))         # HTML gallery, portal thumbnails
```

The index isn't published yet. `CryoetCatalog()` with no argument points at where the monorepo's onboarding batch job will land it. Until then, point it at a local file built with the catalog script:

```python
cat = cryoet.CryoetCatalog(url="/path/to/cryoet-catalog.json")
# or: export SCIGANTIC_CRYOET_CATALOG=/path/to/cryoet-catalog.json
```

## Live reads

`CryoetClient` hits the portal's bucket directly, for a dataset newer than whatever snapshot is loaded, or to double-check a stale field:

```python
client = cryoet.CryoetClient()
client.dataset_metadata(10000)   # full dataset_metadata.json, live
client.runs(10000)               # run directory names, COMPLETE (not sampled)
```

## Data license

The portal describes its data as "publicly available" / "open access" (checked 2026-09-02, portal homepage and Terms of Use), but does not state a specific license designation (CC0, CC-BY, or otherwise) on either page. Check a dataset's own citation/attribution requirements (via `dataset_metadata.json`'s `authors`/`publications` fields, or the portal's own dataset page) before redistributing.

## What this doesn't do (yet)

No synonym/alias expansion in `search()` (a plain "GPCR" won't match "G protein-coupled receptor"); `scigantic-empiar`'s query expansion is the template once this has real query traffic to tune against. No walk of every run per dataset (see the fill-rate table above); if you need every run's metadata for a specific dataset of interest, use `CryoetClient.runs()` plus the official `cryoet-data-portal` client.
