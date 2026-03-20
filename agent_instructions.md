# Shadowbox Agent Instructions

Always follow /docs/uispec.md as the source of truth.

Rules:
- Do not invent features not described in the spec
- Do not create a preset system
- UI must reflect OSCquery structure exactly
- Treat published RNBO instances as the primary UI object
- Use `Patcher` for loadable assets under `/rnbo/patchers/<name>`
- Use `Instance` for live runtime objects under `/rnbo/inst/<n>`
- Avoid the word `Patch` unless quoting external RNBO terminology
- Instance lifecycle UI must be capability-driven from published load/unload command paths
- Add, replace, and remove instance flows must map directly to published backend commands
- Keep system controls separate from per-instance controls
- Do not expose raw instance `config` or `control` branches as generic menus; only surface specific curated capabilities when needed
- Modal editors and selectors should not be overwritten by periodic refresh
- Bool parameters use the bool editor
- Enum parameters always use the enum list selector
- TTID detection should require explicit published metadata `editor: "ttid"`
- Keep implementation simple and minimal
- Prefer small, localized changes over large rewrites

When unsure:
- Ask for clarification instead of guessing
