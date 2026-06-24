# Resources

## Primary sources

- **SPEC.md** — `../SPEC.md` — the original implementation spec; the authoritative "why" behind every design decision
- **Source code** — `../llm-judge/src/llm_judge/` — the canonical truth; lessons reference real line numbers

## Background reading

- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — how `config.py` reads env vars
- [Pydantic BaseModel](https://docs.pydantic.dev/latest/concepts/models/) — how `models.py` data classes work
- [Python ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html) — how `runner.py` parallelises evaluation
- [Anthropic API reference](https://docs.anthropic.com/en/api/messages) — what `llm_client.py` calls under the hood
