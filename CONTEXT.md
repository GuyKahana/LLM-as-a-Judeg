# Glossary — LLM Judge

Canonical domain terms. Implementation details belong in code/docs, not here.

## Storage root
One of the three logical storage areas the judge uses, each independent:
- **Production logs** — input logs, **read-only**. Scanned by lookback or by case ID.
- **Verdicts** — judge output, **write**.
- **Goldens** — calibration examples, **read-only**.

Each root resolves to its own bucket/directory *and* its own backend provider.

## Provider (backend)
The concrete storage technology serving a root: `gcs`, `local`, `s3`, or `azure`.
`STORAGE_PROVIDER` sets the default for every root; a per-root override
(`PRODUCTION_STORAGE_PROVIDER`, `VERDICT_STORAGE_PROVIDER`,
`GOLDEN_STORAGE_PROVIDER`) can give one root a different backend.

## Compute location vs storage location
Two **independent** axes, historically conflated as "local run" vs "cloud run":
- **Compute location** — where the judge *process* runs (laptop vs Cloud Run Job).
- **Storage location** — which provider each root uses.
Running on a laptop does **not** imply local storage, and vice versa.

## Mixed storage
A configuration where the storage roots do not all use the same provider — e.g.
production logs on `gcs` while verdicts are on `local`. Not a backend itself;
it is an emergent combination of per-root provider settings. See
[ADR 0001](docs/adr/0001-per-root-storage-providers.md).
