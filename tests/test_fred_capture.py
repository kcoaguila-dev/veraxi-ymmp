"""
Tests for FredDocumentCaptureAdapter and St. Louis Fed primary data capture.
"""

from pathlib import Path
from PIL import Image

from veraxi_ymmp.epistemic.facts import DocumentCaptureSpec, DocumentProvenance, DocumentSourceType
from veraxi_ymmp.epistemic.fred_capture import FredDocumentCaptureAdapter
from veraxi_ymmp.core.ports import OfficialDocumentCapturePort


def test_fred_protocol_conformance() -> None:
    """Verify FredDocumentCaptureAdapter conforms to OfficialDocumentCapturePort protocol."""
    adapter = FredDocumentCaptureAdapter(prefer_offline=True)
    assert isinstance(adapter, OfficialDocumentCapturePort)
    assert adapter.is_available() is True


def test_fred_synthetic_capture_execution(tmp_path: Path) -> None:
    """Verify offline FRED capture synthesizes valid 16:9 evidence card with synthetic watermark."""
    out_file = tmp_path / "fred_walcl_test.png"
    adapter = FredDocumentCaptureAdapter(prefer_offline=True)

    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.FRED,
        identifier="WALCL",
        target_text="7,450,120",
        source_params={
            "series_title": "Assets: Total Assets (Less Eliminations)",
            "units": "Millions of U.S. Dollars",
        },
    )

    result = adapter.capture_document(spec, out_file)

    assert result.success is True
    assert result.verified is False
    assert result.provenance == DocumentProvenance.SYNTHETIC
    assert result.image_path.is_file()
    assert "WALCL" in result.citation_label
    assert result.metadata["series_id"] == "WALCL"
    assert result.metadata["engine"] == "synthetic_canvas"

    with Image.open(out_file) as img:
        assert img.size == (1200, 675)
        assert img.mode == "RGBA"
    # Sidecar check
    sidecar = out_file.with_suffix(".meta.json")
    assert sidecar.is_file()


def test_fred_user_agent_configuration(monkeypatch) -> None:
    """Verify FRED User-Agent respects environment overrides and avoids fake emails."""
    from veraxi_ymmp.epistemic.fred_capture import get_fred_user_agent

    monkeypatch.setenv("FRED_USER_AGENT", "CustomFredBot/2.0")
    assert get_fred_user_agent() == "CustomFredBot/2.0"

    monkeypatch.delenv("FRED_USER_AGENT", raising=False)
    monkeypatch.setenv("VERAXI_USER_AGENT", "SharedVeraxiBot/1.0")
    assert get_fred_user_agent() == "SharedVeraxiBot/1.0"

    monkeypatch.delenv("VERAXI_USER_AGENT", raising=False)
    ua = get_fred_user_agent()
    assert "VeraxiStudio" in ua
    assert "dev@veraxi.internal" not in ua


class DummyHttpResponse:
    """Mock HTTP response for urllib.request.urlopen."""

    def __init__(self, content: bytes, final_url: str, status: int = 200) -> None:
        self._content = content
        self._final_url = final_url
        self.status = status

    def read(self) -> bytes:
        return self._content

    def geturl(self) -> str:
        return self._final_url

    def __enter__(self) -> "DummyHttpResponse":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


SAMPLE_FRED_CSV = b"DATE,WALCL\n2024-09-25,7450120\n2024-10-02,7435800\n"


def test_fred_live_verified_true_on_legitimate_stlouisfed_response(tmp_path: Path, monkeypatch) -> None:
    """Verify live capture sets verified=True when final URL is verified HTTPS stlouisfed.org."""
    import urllib.request
    from veraxi_ymmp.epistemic.facts import ProvenanceRecord

    dummy_resp = DummyHttpResponse(
        content=SAMPLE_FRED_CSV,
        final_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL",
        status=200,
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: dummy_resp)

    out_file = tmp_path / "fred_live_legit.png"
    adapter = FredDocumentCaptureAdapter(prefer_offline=False)
    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.FRED,
        identifier="WALCL",
    )
    result = adapter.capture_document(spec, out_file)

    assert result.success is True
    assert result.verified is True
    assert result.provenance == DocumentProvenance.LIVE
    assert result.matched_text == "7435800"

    sidecar_p = out_file.with_suffix(".meta.json")
    assert sidecar_p.is_file()
    import json
    with open(sidecar_p, "r", encoding="utf-8") as f:
        data = json.load(f)
    record = ProvenanceRecord.from_dict(data)
    assert record.verified is True
    assert record.provenance == DocumentProvenance.LIVE
    assert record.http_status == 200


def test_fred_live_verified_false_on_redirect_to_untrusted_host(tmp_path: Path, monkeypatch) -> None:
    """Verify live capture sets verified=False when HTTP redirect lands on non-stlouisfed host."""
    import urllib.request

    dummy_resp = DummyHttpResponse(
        content=SAMPLE_FRED_CSV,
        final_url="https://attacker.com/stlouisfed.org/fake.csv",
        status=200,
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: dummy_resp)

    out_file = tmp_path / "fred_redirect_evil.png"
    adapter = FredDocumentCaptureAdapter(prefer_offline=False)
    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.FRED,
        identifier="WALCL",
    )
    result = adapter.capture_document(spec, out_file)

    assert result.success is True
    assert result.verified is False  # Refuses verified status due to untrusted host!
    assert result.provenance == DocumentProvenance.LIVE


def test_fred_live_verified_false_on_dot_boundary_bypass(tmp_path: Path, monkeypatch) -> None:
    """Verify dot-boundary prevents evilstlouisfed.org spoofing from being verified."""
    import urllib.request

    dummy_resp = DummyHttpResponse(
        content=SAMPLE_FRED_CSV,
        final_url="https://evilstlouisfed.org/graph/fredgraph.csv?id=WALCL",
        status=200,
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: dummy_resp)

    out_file = tmp_path / "fred_dot_boundary.png"
    adapter = FredDocumentCaptureAdapter(prefer_offline=False)
    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.FRED,
        identifier="WALCL",
    )
    result = adapter.capture_document(spec, out_file)

    assert result.success is True
    assert result.verified is False


def test_fred_live_fails_gracefully_on_network_error(tmp_path: Path, monkeypatch) -> None:
    """Verify network error produces success=False and verified=False."""
    import urllib.request
    import urllib.error

    def mock_fail(req, timeout=15):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_fail)

    out_file = tmp_path / "fred_network_fail.png"
    adapter = FredDocumentCaptureAdapter(prefer_offline=False)
    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.FRED,
        identifier="WALCL",
    )
    result = adapter.capture_document(spec, out_file)

    assert result.success is False
    assert result.verified is False
    assert "Connection refused" in result.error_message
