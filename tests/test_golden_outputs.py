"""Golden-output regression test (Phase 1 refactor baseline).

The .ymmp JSON and the TimelineIR dump for one sample project were captured
before the ``ProjectPipeline.run`` / ``MoviePyRenderer.render`` refactor
(``scripts/capture_golden.py``). The refactor — and every later change —
must leave them byte-identical.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from capture_golden import capture  # noqa: E402

GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "golden"


def test_golden_outputs_byte_identical(tmp_path: Path) -> None:
    capture(tmp_path)
    for name in ("sample.ymmp", "ir_dump.json"):
        expected = (GOLDEN_DIR / name).read_bytes()
        actual = (tmp_path / name).read_bytes()
        assert actual == expected, (
            f"Golden output {name} changed. If this change is intentional, "
            "regenerate with: python scripts/capture_golden.py"
        )
