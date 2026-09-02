# Changelog

## 0.1.2

Adds `CryoetCatalog.with_emdb()`/`with_empiar()`: join CryoET Data Portal
datasets to the EMDB structures and EMPIAR raw deposits they cite, via
the ids already carried on each catalog row. Requires the new `bridge`
extra (`pip install "scigantic-cryoet[bridge]"`), which pulls in
`scigantic-emdb`/`scigantic-empiar`; both methods raise `RuntimeError`
if the sibling package isn't installed rather than returning an empty,
misleadingly "no cross-references" result.

Measured against the full portal: 160 dataset-to-EMDB pairs across 45
datasets, 27 dataset-to-EMPIAR pairs across 24 datasets, verified live
against both sibling catalogs.

## 0.1.1

Metadata/docs only, no code change. The 0.1.0 tag was cut before a pass
that removed em-dashes and mid-sentence " -- " breaks from the README,
CHANGELOG, and every docstring, so the package published to PyPI from
that tag still carried them. Also fixed two README example queries
that returned zero real results against the live catalog.

## 0.1.0

First release. `CryoetCatalog` (search/filter over a pre-built index of the
CZ CryoET Data Portal, honest about which fields are complete-per-dataset
versus sampled from one run), `CryoetClient` (live `dataset_metadata.json`
and run-listing reads against the portal's public bucket, anonymous, no
credentials).

The catalog index itself is not yet published. `CryoetCatalog()` points at
where the monorepo's onboarding batch job will land it; pass a local file
meanwhile. See README.
