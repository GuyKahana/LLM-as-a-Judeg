# Bundled golden examples

Fallback golden examples shipped *inside the package*. They are used by
`llm_judge.golden_examples.load_golden_examples` **only when the golden storage
root returns zero examples** for a given prompt type — the bucket is always the
primary source. See `src/llm_judge/golden_examples.py`.

## Layout

One subdirectory per **rubric name** (the same key the registry maps filenames
to — see `src/llm_judge/rubrics/registry.py`), containing one or more `.json`
files:

```
golden/
├── full_summary/
│   ├── example1.json
│   └── example2.json
├── sick_permits/
│   └── example1.json
└── medical_document_validator/
    └── example1.json
```

Files are read in sorted filename order and capped at `JUDGE_GOLDEN_EXAMPLES_MAX`
(default 2). The directory name **must** match a rubric name exactly, or the
examples will never be found.

## Contract

Each JSON file is one golden turn and **must** contain:

- `"expected_verdict": "pass"` — goldens are always positive (high-quality)
  examples used to calibrate the judge's scoring.

A typical golden mirrors a production log turn, e.g.:

```json
{
  "prompt": "…the production system prompt…",
  "input": "…the production input…",
  "output": "…a high-quality output…",
  "expected_verdict": "pass"
}
```

The `prompt` field is stripped before the example is sent to the judge (it bloats
the request without aiding calibration), so it is optional but harmless.

## Committing examples

The repository's `.gitignore` ignores `*.json` broadly (to keep credentials and
PII out of git); this directory is explicitly re-included via
`!src/llm_judge/rubrics/golden/**/*.json`. Plain `git add` works — no `-f`
needed. **Do not** commit any example containing real patient data; goldens must
be synthetic or fully de-identified.
