# Schema variant and rubric name are independent concepts

The user caught an error in lesson 1 where `filter_diagnoses.json` was incorrectly labelled as `boundary_check` schema. Looking at the real file, it has a `prompt` key and a dict `output` — which makes it `tool_use`. The lesson had confused the rubric name (`grouping_boundary`) with the schema variant name (`boundary_check`).

This matters for future sessions: the user demonstrated they can read real JSON and apply the detection logic from `log_parser.py` correctly. They understand that schema variant (detected from JSON keys) and rubric name (detected from filename via the registry) are two separate axes. Don't re-explain this distinction — it's solid.

**Implications:** Lesson 2 can assume the user knows the four schema variants and can correctly classify a file given its JSON structure.
