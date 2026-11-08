"""
Tests for WebDocumentCaptureAdapter and general web document capture.
"""

from pathlib import Path
from PIL import Image

from veraxi_ymmp.app.cli_capture import cmd_capture
from veraxi_ymmp.epistemic.facts import DocumentCaptureSpec, DocumentProvenance, DocumentSourceType
from veraxi_ymmp.core.ports import OfficialDocumentCapturePort
from veraxi_ymmp.epistemic.web_capture import WebDocumentCaptureAdapter


def test_web_protocol_conformance() -> None:
    """Verify WebDocumentCaptureAdapter conforms to OfficialDocumentCapturePort protocol."""
    adapter = WebDocumentCaptureAdapter(prefer_offline=True)
    assert isinstance(adapter, OfficialDocumentCapturePort)
    assert adapter.is_available() is True


def test_web_synthetic_capture_execution(tmp_path: Path) -> None:
    """Verify offline web capture synthesizes valid 16:9 evidence card with synthetic watermark."""
    out_file = tmp_path / "web_python_test.png"
    adapter = WebDocumentCaptureAdapter(prefer_offline=True)

    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.WEB,
        identifier="https://en.wikipedia.org/wiki/Python_(programming_language)",
        target_text="Guido van Rossum",
        citation_label="Wikipedia: Python (programming language)",
    )

    result = adapter.capture_document(spec, out_file)

    assert result.success is True
    assert result.verified is False
    assert result.provenance == DocumentProvenance.SYNTHETIC
    assert result.image_path.is_file()
    assert "Wikipedia" in result.citation_label
    assert result.matched_text == "Guido van Rossum"

    with Image.open(out_file) as img:
        assert img.size == (1200, 675)
        assert img.mode == "RGBA"


def test_cli_capture_web_mock(tmp_path: Path) -> None:
    """Verify CLI capture command with --source web and --mock."""
    out_png = tmp_path / "cli_web_proof.png"
    argv = [
        "--source", "web",
        "--url", "https://en.wikipedia.org/wiki/Python",
        "--target", "Guido van Rossum",
        "--mock",
        "--out", str(out_png),
    ]
    cmd_capture(argv)
    assert out_png.is_file()
