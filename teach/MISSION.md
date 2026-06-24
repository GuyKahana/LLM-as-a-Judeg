# Mission: Understanding the LLM-as-a-Judge Project

## Why
You built this service with Claude Code and want to own it — to understand what every module does, why it exists, and how data flows through the whole system. The goal is to be able to explain, modify, and extend any part of it confidently.

## Success looks like
- Can describe what each module in `src/llm_judge/` does in one sentence without looking
- Can trace a single log file through the system from GCS read to verdict write
- Can explain the storage abstraction layer and why it exists
- Can explain what a rubric is and how the registry maps filenames to rubrics
- Can describe the four log schema variants and how `log_parser.py` handles them
- Can explain how the evaluator handles LLM parse failures

## Constraints
- Learning from the actual codebase — not abstract theory
- Lessons should be anchored to real files and real line numbers

## Out of scope
- Generic Python tutorials
- How to extend the system with new features (until the architecture is solid)
