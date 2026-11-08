"""
Unit tests for SEC EDGAR and Official Document Capture Engine.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image

from veraxi_ymmp.epistemic.facts import DocumentCaptureResult, DocumentCaptureSpec, DocumentSourceType
from veraxi_ymmp.core.ports import OfficialDocumentCapturePort
from veraxi_ymmp.epistemic.edgar_capture import (
    EdgarDocumentCaptureAdapter,
    get_sec_user_agent,
    resolve_company_meta,
    DEFAULT_SEC_USER_AGENT,
)


def test_protocol_conformance() -> None:
    """Verify that EdgarDocumentCaptureAdapter satisfies OfficialDocumentCapturePort."""
    adapter = EdgarDocumentCaptureAdapter(prefer_offline=True)
    assert isinstance(adapter, OfficialDocumentCapturePort)
    assert adapter.is_available() is True


def test_domain_models_creation() -> None:
    """Verify DocumentCaptureSpec and DocumentCaptureResult initialization."""
    spec = DocumentCaptureSpec(
        source_type=DocumentSourceType.SEC_EDGAR,
        identifier="MSFT",
        target_text="Operating income",
        source_params={
            "form": "10-K",
            "company_name": "MICROSOFT CORPORATION",
        },
    )
    assert spec.identifier == "MSFT"
    assert spec.source_params.get("form") == "10-K"
    assert spec.source_type == DocumentSourceType.SEC_EDGAR

    result = DocumentCaptureResult(
        success=True,
        image_path=Path("dummy.png"),
        citation_label="SEC 10-K",
        source_url="https://sec.gov",
    )
    assert result.success is True
    assert result.citation_label == "SEC 10-K"


def test_sec_user_agent_environment_resolution(monkeypatch) -> None:
    """Verify SEC_USER_AGENT safely reads from environment variable or defaults gracefully."""
    # Custom configured agent
    test_agent = "SampleApp Research contact@example.com"
    monkeypatch.setenv("SEC_USER_AGENT", test_agent)
    assert get_sec_user_agent() == test_agent

    # Fallback when env var is absent
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert get_sec_user_agent() == DEFAULT_SEC_USER_AGENT


def test_resolve_company_meta() -> None:
    """Verify ticker-to-CIK mapping."""
    cik_msft, name_msft = resolve_company_meta("msft")
    assert cik_msft == "0000789019"
    assert "MICROSOFT" in name_msft

    cik_aapl, name_aapl = resolve_company_meta("AAPL")
    assert cik_aapl == "0000320193"
    assert "APPLE" in name_aapl

    cik_num, name_num = resolve_company_meta("12345")
    assert cik_num == "0000012345"


def test_synthetic_capture_execution(tmp_path: Path) -> None:
    """Verify offline document capture synthesizes valid 16:9 document card."""
    out_file = tmp_path / "sec_proof_test.png"
    adapter = EdgarDocumentCaptureAdapter(prefer_offline=True)

    spec = DocumentCaptureSpec(
        identifier="MSFT",
        target_text="Capital expenditures",
        source_params={
            "form": "10-Q",
            "accession_number": "0000789019-24-000012",
            "company_name": "MICROSOFT CORPORATION",
        },
    )

    result = adapter.capture_document(spec, out_file)

    assert result.success is True
    assert result.image_path.is_file()
    assert "MICROSOFT CORPORATION" in result.citation_label
    assert "0000789019" in result.metadata["cik"]
    assert result.metadata["engine"] == "synthetic_canvas"

    with Image.open(out_file) as img:
        assert img.size == (1200, 675)
        assert img.mode == "RGBA"


def test_cli_capture_sec_mock(tmp_path: Path) -> None:
    """Verify CLI capture-sec subcommand in mock mode."""
    from veraxi_ymmp.app.cli import _cmd_capture_sec

    out_file = tmp_path / "cli_capture_out.png"
    _cmd_capture_sec([
        "--ticker", "NVDA",
        "--form", "10-K",
        "--search", "Data Center revenue",
        "--company", "NVIDIA CORPORATION",
        "--out", str(out_file),
        "--mock",
    ])

    assert out_file.is_file()
    with Image.open(out_file) as img:
        assert img.size == (1200, 675)

def test_cli_capture_generic_fred_mock(tmp_path: Path) -> None:
    """Verify CLI capture subcommand with --source fred in mock mode."""
    from veraxi_ymmp.app.cli import _cmd_capture

    out_file = tmp_path / "cli_capture_fred.png"
    _cmd_capture([
        "--source", "fred",
        "--identifier", "FEDFUNDS",
        "--title", "Federal Funds Effective Rate",
        "--target", "5.33",
        "--out", str(out_file),
        "--mock",
    ])

    assert out_file.is_file()
    with Image.open(out_file) as img:
        assert img.size == (1200, 675)



def test_live_failure_must_not_silently_fallback_to_synthetic(tmp_path: Path, monkeypatch) -> None:
    """Verify that a live capture failure fails fast and does NOT return fake synthetic proof."""
    monkeypatch.setenv("SEC_USER_AGENT", "VeraxiTest test@example.com")
    out_file = tmp_path / "live_fail.png"
    # Live mode with an unreachable URL
    adapter = EdgarDocumentCaptureAdapter(prefer_offline=False)
    spec = DocumentCaptureSpec(
        identifier="NVDA",
        document_url="https://www.sec.gov/Archives/edgar/data/unreachable_nonexistent_filing.htm",
        target_text="NonExistentMetric12345",
    )
    result = adapter.capture_document(spec, out_file)
    assert result.success is False
    assert result.verified is False
    assert result.provenance == "live"
    assert len(result.error_message) > 0
    assert not out_file.exists()


def test_synthetic_capture_must_never_claim_verified(tmp_path: Path) -> None:
    """Verify that synthetic capture sets verified=False and provenance=synthetic."""
    out_file = tmp_path / "synthetic_test.png"
    adapter = EdgarDocumentCaptureAdapter(prefer_offline=True)
    spec = DocumentCaptureSpec(
        identifier="MSFT",
        target_text="Capital expenditures",
        source_params={
            "accession_number": "0000789019-24-000012",
            "company_name": "MICROSOFT CORPORATION",
        },
    )
    result = adapter.capture_document(spec, out_file)
    assert result.success is True
    assert result.verified is False
    assert result.provenance == "synthetic"


def test_missing_accession_must_not_fabricate_microsoft_number(tmp_path: Path) -> None:
    """Verify that omitting accession number does not default to MSFT's 0000789019-24-000012."""
    out_file = tmp_path / "nvda_no_acc.png"
    adapter = EdgarDocumentCaptureAdapter(prefer_offline=True)
    spec = DocumentCaptureSpec(
        identifier="NVDA",
        target_text="Compute & Networking",
        source_params={
            "company_name": "NVIDIA CORPORATION",
        },
    )
    result = adapter.capture_document(spec, out_file)
    assert "0000789019-24-000012" not in result.citation_label
    assert result.metadata.get("accession_number") != "0000789019-24-000012"


def test_live_sec_request_requires_valid_user_agent(tmp_path: Path, monkeypatch) -> None:
    """Verify that live SEC requests refuse requests if SEC_USER_AGENT is default/unconfigured."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    out_file = tmp_path / "sec_no_ua.png"
    adapter = EdgarDocumentCaptureAdapter(prefer_offline=False)
    spec = DocumentCaptureSpec(
        identifier="MSFT",
        document_url="https://www.sec.gov/ix?doc=/Archives/edgar/data/789019/000078901924000012/msft-20240331.htm",
        target_text="Operating income",
    )
    result = adapter.capture_document(spec, out_file)
    assert result.success is False
    assert "SEC_USER_AGENT" in result.error_message
