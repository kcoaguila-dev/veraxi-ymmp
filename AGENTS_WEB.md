# Veraxi YMMP — Web Rules (slim)

You are editing veraxi-ymmp in a web chat. The bundle already contains
the complete files; reply per the bundle's Reply Format section. This
file distills AGENTS.md sections 1–2 for copy/paste work; AGENTS.md
remains the full governance text.

## Architecture (non-negotiable)

- 3-tier compiler DAG; dependencies flow down only:
  `core/` [Tier 1: pure AST/IR, ports — imports nothing above it];
  `epistemic/`, `editorial/`, `graphics/`, `audio/`, `exporters/`
  [Tier 2]; `app/` [Tier 3: orchestration, CLI].
- Tier 2 packages must never import from `app/`. `core/` must not
  import Tier 2 or Tier 3. Exporters must not import peer exporters.
- Python files: 100–900 lines (hard ceiling 900); functions ≤ 120
  lines. A package root holds only `__init__.py` and `__main__.py`;
  no single-purpose micro-files to dodge the ceiling.
- Compiler gates fail closed (epistemic fact checks, editorial
  typography/retention, architectural fitness). Never weaken a gate
  to make output pass.

## Privacy and time

- No local machine paths, usernames, emails, or secrets in any file;
  `scripts/check_no_local_paths.py` must pass.
- The current year is 2026. Sources older than 12 months need
  explicit historical framing; never treat 2023–2025 as the
  current year.

## Quality bar

- `ruff check` and `mypy` must pass on every file you return.
  Type-annotate new functions and match the file's existing style.
- Preserve Japanese text exactly — wording, ruby tags such as
  {Kanji|ruby}, and punctuation. Every number on a slide or in a
  script must trace to a supported claim; do not invent figures.

## Web-chat working rules

- Do not edit tests or prompt templates unless the task explicitly
  says so.
- Return complete files only: no diffs, no truncation, and no
  "rest unchanged" placeholders. Apply rejects elided replies,
  empty replacements, and — for files of 30+ lines — replacements
  under 60% of the original line count (override: --allow-shrink).
- State any assumption you could not verify from the bundle instead
  of guessing silently.
- If the full reply does not fit in one message, say so; never cut
  a file short mid-block.
