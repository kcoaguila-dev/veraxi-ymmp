"""Capture golden outputs for the Phase 1 refactor baseline.

Regenerates the golden files for one sample project
(``tests/fixtures/sample_script.json`` + ``sample_template.ymmp``):

- ``tests/fixtures/golden/sample.ymmp`` — the compiled .ymmp JSON, byte-exact.
- ``tests/fixtures/golden/ir_dump.json`` — a canonical dump of the TimelineIR.

``tests/test_golden_outputs.py`` regenerates both into a temp directory and
asserts byte identity, so any refactor of ``ProjectPipeline.run`` /
``MoviePyRenderer.render`` (or the compiler pipeline beneath them) that
changes observable output fails loudly.

Usage:
    python scripts/capture_golden.py [output_dir]
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from veraxi_ymmp.app.compiler import YMMPCompiler  # noqa: E402


def ir_to_data(obj: Any) -> Any:
    """Convert a TimelineIR (dataclasses / Paths) into canonical JSON data."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: ir_to_data(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): ir_to_data(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [ir_to_data(v) for v in obj]
    return obj


def capture(outdir: Path) -> None:
    fixtures = REPO_ROOT / "tests" / "fixtures"
    template = fixtures / "sample_template.ymmp"
    script = json.loads((fixtures / "sample_script.json").read_text(encoding="utf-8"))
    outdir.mkdir(parents=True, exist_ok=True)

    compiler = YMMPCompiler(str(template))
    ir, _audio = compiler.build_ir(script, outdir / "audio")
    (outdir / "ir_dump.json").write_text(
        json.dumps(ir_to_data(ir), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )

    compiler2 = YMMPCompiler(str(template))
    compiler2.compile(script, str(outdir / "sample.ymmp"))


def main() -> None:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "tests" / "fixtures" / "golden"
    capture(outdir)
    print(f"Golden outputs written to {outdir}")


if __name__ == "__main__":
    main()
