# ADR 0002 — Co-location is the storage convention

**Status:** Accepted
**Date:** 2026-06-24

## Context

[ADR 0001](0001-per-root-storage-providers.md) gave each storage root its own
backend, so the judge *can* mix providers freely — e.g. read production logs
from GCS while writing verdicts to local disk. That flexibility raised a
follow-up question the mechanism alone does not answer: **is mixing backends a
supported steady state, or a stepping stone?**

The distinction matters because nothing in the code stops a fully-mixed
configuration, and a reasonable engineer could assume mixing is a first-class
mode to build around (a dashboard verdict-source toggle, per-root UI controls,
documentation of every combination, etc.). It also caused real confusion: a
hybrid setup (cloud logs, local verdicts) plus a relative `LOCAL_STORAGE_BASE_DIR`
made local runs appear to "vanish" from the dashboard, because compute location
and storage location had been mentally conflated.

## Decision

Treat **co-location** as the operating convention: the judge reads and writes
from the same place it runs — **all `local` in development, all cloud once fully
deployed**. The per-root providers remain available, but **mixed storage is a
transitional migration aid** (e.g. seeding local verdicts/goldens from cloud
logs), not the steady state. A fully-deployed system uses one provider for every
root.

Consequently, "local" actions are forced fully local (all three roots), rather
than only switching the production root — see the dashboard's `local_run_env()`.

## Alternatives considered

- **Make mixed storage a first-class, fully-supported mode.** Add per-root
  source toggles across the dashboard (verdict views, runs, upload) so any
  combination is browsable in one session. Rejected: it roughly doubles the
  config and UI surface, and every combination becomes a state to test and
  document — for a capability that is only needed during migration.

## Consequences

- Compute and storage are **independent by mechanism but co-located by policy**
  (recorded in `CONTEXT.md`). New work should assume co-location unless
  explicitly doing a migration.
- A local run is self-contained: logs, verdicts, and goldens all land locally,
  so a local dashboard shows them without extra toggles.
- The flexibility from ADR 0001 is preserved but deliberately *not* surfaced as
  a product feature; this ADR exists so the next engineer does not build out
  full mixed-storage support assuming it was intended.
