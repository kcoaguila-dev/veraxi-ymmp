"""
Tests for CitationCardRenderer and typed BadgeKind invariants.
"""

from pathlib import Path
from PIL import Image

from veraxi_ymmp.citation_card import (
    BadgeKind,
    CitationCardRenderer,
    resolve_badge_kind,
)
from veraxi_ymmp.facts import DocumentProvenance


def test_resolve_badge_kind_state_matrix() -> None:
    """Verify that synthetic provenance can NEVER produce VERIFIED_PRIMARY badge."""
    # Synthetic must always yield SYNTHETIC_MOCK regardless of verified flag
    assert resolve_badge_kind(verified=False, provenance=DocumentProvenance.SYNTHETIC) == BadgeKind.SYNTHETIC_MOCK
    assert resolve_badge_kind(verified=True, provenance=DocumentProvenance.SYNTHETIC) == BadgeKind.SYNTHETIC_MOCK

    # Live unverified yields UNVERIFIED_SOURCE
    assert resolve_badge_kind(verified=False, provenance=DocumentProvenance.LIVE) == BadgeKind.UNVERIFIED_SOURCE

    # Live verified yields VERIFIED_PRIMARY
    assert resolve_badge_kind(verified=True, provenance=DocumentProvenance.LIVE) == BadgeKind.VERIFIED_PRIMARY


def test_citation_card_rendering_dimensions(tmp_path: Path) -> None:
    """Verify CitationCardRenderer generates 1200x675 RGBA canvas."""
    renderer = CitationCardRenderer(1200, 675)
    dummy_raw = tmp_path / "dummy_raw.png"
    Image.new("RGBA", (400, 200), (254, 240, 138, 255)).save(dummy_raw)

    out_card = tmp_path / "card_out.png"
    result_path = renderer.render_card(
        raw_image_path=dummy_raw,
        out_path=out_card,
        agency_title="U.S. SECURITIES AND EXCHANGE COMMISSION",
        header_meta="CIK: 0000789019 | FORM 10-Q",
        entity_title="MICROSOFT CORPORATION",
        subtitle="Official Accession: 0000789019-24-000012",
        citation_label="SEC EDGAR Form 10-Q | MICROSOFT CORPORATION",
        badge_kind=BadgeKind.VERIFIED_PRIMARY,
    )

    assert result_path.is_file()
    with Image.open(result_path) as img:
        assert img.size == (1200, 675)
        assert img.mode == "RGBA"


def test_metric_card_rendering_dimensions(tmp_path: Path) -> None:
    """Verify render_metric_card generates 1200x675 RGBA canvas for statistical series."""
    renderer = CitationCardRenderer(1200, 675)
    out_card = tmp_path / "metric_card_out.png"

    result_path = renderer.render_metric_card(
        out_path=out_card,
        agency_title="FEDERAL RESERVE BANK OF ST. LOUIS | FRED ECONOMIC DATA",
        header_meta="SERIES ID: WALCL",
        entity_title="Assets: Total Assets",
        subtitle="Units: Millions of U.S. Dollars",
        observation_value="7,450,120",
        observation_date="2024-10-01",
        citation_label="St. Louis Fed FRED | WALCL",
        badge_kind=BadgeKind.VERIFIED_PRIMARY,
    )

    assert result_path.is_file()
    with Image.open(result_path) as img:
        assert img.size == (1200, 675)
        assert img.mode == "RGBA"
