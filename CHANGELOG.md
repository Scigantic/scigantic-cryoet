# Changelog

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
