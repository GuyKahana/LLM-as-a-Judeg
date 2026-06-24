# ADR 0001 — Per-root storage providers

**Status:** Accepted
**Date:** 2026-06-24

## Context

`StorageClient` uses three independent storage roots — production logs (read),
verdicts (write), and goldens (read). They have always been three separate
`StorageProvider` instances, but `create_provider` read one global setting
(`STORAGE_PROVIDER`), forcing all three onto the same backend: everything on GCS
or everything on local disk, never a mix.

A real need surfaced: run the judge on a laptop, read production logs from GCS
(including the lookback scan), but write verdicts to local disk because no
verdict bucket exists yet. The global switch could not express this — compute
location and storage location are independent axes, and storage roots can
legitimately differ from one another.

## Decision

Let each root choose its own backend. Add three optional settings —
`PRODUCTION_STORAGE_PROVIDER`, `VERDICT_STORAGE_PROVIDER`,
`GOLDEN_STORAGE_PROVIDER` — each falling back to `STORAGE_PROVIDER` when unset
(golden falls back to the verdict provider, mirroring how `GOLDEN_BUCKET`
defaults to `VERDICT_BUCKET`). A model validator resolves them to concrete
strings, and `create_provider` takes an explicit `provider` argument.

## Alternatives considered

- **`STORAGE_PROVIDER=hybrid` magic value.** Hard-codes one combination
  (gcs prod, local rest) behind a word that is not a real backend. Inflexible —
  every new combination needs a new word — and it overloads a variable whose
  values are otherwise concrete technologies. Rejected.

## Consequences

- "Mixed storage" is now an emergent combination of plain settings, not a
  special mode; any per-root mix of `gcs`/`local`/`s3`/`azure` works.
- Fully backward compatible: omit the overrides and behaviour is identical to
  the single global switch.
- Three more env vars to document and reason about. The validator keeps the
  fallback logic in one place so `StorageClient` stays unaware of it.
