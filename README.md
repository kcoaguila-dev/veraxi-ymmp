# veraxi_ymmp

**Disclaimer: Output has not been validated by opening in a real YMM4 install. Before trusting this for real work, open a generated `output.ymmp` in YMM4 and confirm it loads and plays correctly.**

A Python tool that generates YMM4 `.ymmp` dialogue timelines by cloning real template items.

## Out of scope for v1
- Synthesizing real audio and computing exact frame durations from it. Length currently uses a placeholder timing heuristic (`max(30, len(text) * 5)`). Replace once real TTS duration measurement is validated against actual YMM4 behavior.
- Building `Characters`, `VideoInfo`, or any top-level structure — these pass through from the template untouched.
- Multi-emotion/expression switching via `TachieFaceParameter` — left exactly as copied from the template.
- Any C#/.NET plugin work, or a `.ymme` distributable.
