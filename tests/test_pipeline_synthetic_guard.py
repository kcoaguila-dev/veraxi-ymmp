"""
Tests for Fail-Closed Asset Provenance Guard and Pipeline Synthetic Protection.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image
import pytest

from veraxi_ymmp.asset_guard import (
    AssetIntegrityError,
    compute_file_sha256,
    verify_image_asset,
    verify_project_assets,
    write_provenance_metadata,
)
from veraxi_ymmp.facts import DocumentProvenance, DocumentSourceType, ProvenanceRecord
from veraxi_ymmp.pipeline import ProjectPipeline


def _create_dummy_png(path: Path, color=(15, 23, 42, 255)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (100, 100), color)
    img.save(path)
    return path


def _create_sidecar(
    image_path: Path,
    provenance: DocumentProvenance,
    verified: bool,
    tampered_hash: bool = False,
    schema_version: str = "1.0",
) -> Path:
    img_bytes = image_path.read_bytes()
    img_hash = hashlib.sha256(img_bytes).hexdigest()
    if tampered_hash:
        img_hash = "0" * 64

    record = ProvenanceRecord(
        schema_version=schema_version,
        image_path=str(image_path),
        image_sha256=img_hash,
        content_sha256="test_content_hash",
        source_type=DocumentSourceType.SEC_EDGAR,
        identifier="MSFT",
        citation_label="SEC EDGAR 10-Q",
        source_url="https://www.sec.gov/edgar/test.htm",
        final_url="https://www.sec.gov/edgar/test.htm",
        http_status=200,
        verified=verified,
        provenance=provenance,
        retrieved_at="2026-11-04T00:00:00Z",
        matched_text="Capex",
    )
    sidecar_path = image_path.with_suffix(".meta.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)
    return sidecar_path


def test_missing_sidecar_for_official_asset_fails(tmp_path: Path) -> None:
    """Official assets without a .meta.json sidecar must fail closed."""
    img_p = _create_dummy_png(tmp_path / "assets" / "official" / "sec_capex.png")

    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_image_asset(img_p, allow_synthetic=False, require_sidecar=True)
    assert "Missing mandatory provenance sidecar" in str(exc_info.value)


def test_tampered_asset_hash_mismatch_fails(tmp_path: Path) -> None:
    """If the PNG bytes do not match the sidecar's image_sha256, it must fail closed."""
    img_p = _create_dummy_png(tmp_path / "test_img.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.LIVE, verified=True, tampered_hash=True)

    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_image_asset(img_p, allow_synthetic=False, require_sidecar=True)
    assert "Tampered asset detected" in str(exc_info.value)


def test_synthetic_mock_blocked_in_production_run(tmp_path: Path) -> None:
    """Synthetic mocks must be rejected when allow_synthetic=False."""
    img_p = _create_dummy_png(tmp_path / "sec_mock.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.SYNTHETIC, verified=False)

    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_image_asset(img_p, allow_synthetic=False, require_sidecar=True)
    assert "Production pipeline blocked synthetic mock asset" in str(exc_info.value)


def test_unverified_source_blocked_in_production_run(tmp_path: Path) -> None:
    """Live but unverified assets must be rejected when allow_synthetic=False."""
    img_p = _create_dummy_png(tmp_path / "unverified_feed.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.LIVE, verified=False)

    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_image_asset(img_p, allow_synthetic=False, require_sidecar=True)
    assert "Production pipeline blocked unverified asset" in str(exc_info.value)


def test_synthetic_mock_allowed_when_flag_enabled(tmp_path: Path) -> None:
    """Synthetic mocks must pass when allow_synthetic=True."""
    img_p = _create_dummy_png(tmp_path / "sec_mock.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.SYNTHETIC, verified=False)

    record = verify_image_asset(img_p, allow_synthetic=True, require_sidecar=True)
    assert record is not None
    assert record.provenance == DocumentProvenance.SYNTHETIC


def test_unverified_non_official_asset_without_sidecar_allowed(tmp_path: Path) -> None:
    """Normal background or user avatar without sidecar is permitted if require_sidecar=False."""
    img_p = _create_dummy_png(tmp_path / "bg_normal.png")
    record = verify_image_asset(img_p, allow_synthetic=False, require_sidecar=False)
    assert record is None


def test_pipeline_refuses_project_with_synthetic_official_asset(tmp_path: Path) -> None:
    """ProjectPipeline.run must abort if an official asset is synthetic and allow_synthetic=False."""
    proj_dir = tmp_path / "test_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)

    script_data = [
        {"character": "metan", "text": "Testing proof asset.", "image": "official_proof.png"}
    ]
    with open(proj_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f)

    img_p = _create_dummy_png(proj_dir / "official_proof.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.SYNTHETIC, verified=False)

    pipeline = ProjectPipeline(use_tts=False)
    result = pipeline.run(
        proj_dir,
        do_premiere=False,
        do_ymmp=False,
        do_qa=False,
        do_thumbnail=False,
        allow_synthetic=False,
    )

    assert result.success is False
    assert any("blocked synthetic mock asset" in err for err in result.errors)


def test_pipeline_accepts_project_with_synthetic_when_allowed(tmp_path: Path) -> None:
    """ProjectPipeline.run must proceed past guard when allow_synthetic=True."""
    proj_dir = tmp_path / "test_proj_allowed"
    proj_dir.mkdir(parents=True, exist_ok=True)

    script_data = [
        {"character": "metan", "text": "Testing proof asset.", "image": "official_proof.png"}
    ]
    with open(proj_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f)

    img_p = _create_dummy_png(proj_dir / "official_proof.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.SYNTHETIC, verified=False)

    pipeline = ProjectPipeline(use_tts=False)
    result = pipeline.run(
        proj_dir,
        do_premiere=False,
        do_ymmp=False,
        do_qa=False,
        do_thumbnail=False,
        allow_synthetic=True,
    )

    assert not any("blocked synthetic mock asset" in err for err in result.errors)


def test_compute_file_sha256_matches_hashlib(tmp_path: Path) -> None:
    """Verify compute_file_sha256 matches standard hashlib digest."""
    test_file = tmp_path / "sample.bin"
    test_file.write_bytes(b"Veraxi cryptographic test payload")
    assert compute_file_sha256(test_file) == hashlib.sha256(b"Veraxi cryptographic test payload").hexdigest()



def test_synthetic_png_without_sidecar_blocked_by_embedded_chunk(tmp_path: Path) -> None:
    """A synthetic PNG stripped of its sidecar must still be blocked via embedded metadata."""
    img_p = _create_dummy_png(tmp_path / "chart_without_sidecar.png")
    record = ProvenanceRecord(
        schema_version="1.0",
        image_path=str(img_p),
        image_sha256="dummy",
        content_sha256="dummy",
        source_type=DocumentSourceType.FRED,
        identifier="M2SL",
        citation_label="FRED M2SL",
        source_url="https://fred.stlouisfed.org/series/M2SL",
        final_url="https://fred.stlouisfed.org/series/M2SL",
        http_status=200,
        verified=False,
        provenance=DocumentProvenance.SYNTHETIC,
        retrieved_at="2026-11-04T00:00:00Z",
    )
    sidecar_path = write_provenance_metadata(img_p, record, embed_in_png=True)
    assert sidecar_path.is_file()

    # Now simulate stripping the sidecar file
    sidecar_path.unlink()
    assert not sidecar_path.exists()

    # Even though require_sidecar=False and sidecar does not exist, embedded chunk must catch it
    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_image_asset(img_p, allow_synthetic=False, require_sidecar=False)
    assert "detected via embedded PNG metadata" in str(exc_info.value)


def test_missing_referenced_asset_in_script_fails_closed(tmp_path: Path) -> None:
    """If a script entry references a non-existent file, the guard must fail closed."""
    script_entries = [
        {"character": "ずんだもん", "text": "幻の資産なのだ！", "image": "non_existent_chart.png"}
    ]
    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_project_assets(tmp_path, script_entries=script_entries, allow_synthetic=False)
    assert "Script cut references non-existent asset" in str(exc_info.value)


def test_missing_referenced_asset_in_broll_manifest_fails_closed(tmp_path: Path) -> None:
    """If a broll manifest slide references a non-existent asset, the guard must fail closed."""
    manifest = {
        "slides": [
            {"id": "slide_1", "type": "official_data", "image_path": "missing_macro.png"}
        ]
    }
    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_project_assets(tmp_path, broll_manifest=manifest, allow_synthetic=False)
    assert "Slide references non-existent asset" in str(exc_info.value)


def test_official_non_png_asset_requires_sidecar(tmp_path: Path) -> None:
    """Official non-PNG images (JPG/WebP) under assets/official must enforce sidecars."""
    off_dir = tmp_path / "assets" / "official"
    off_dir.mkdir(parents=True, exist_ok=True)
    jpg_path = off_dir / "fed_chart.jpg"
    img = Image.new("RGB", (100, 100), (20, 30, 40))
    img.save(jpg_path)

    with pytest.raises(AssetIntegrityError) as exc_info:
        verify_project_assets(tmp_path, allow_synthetic=False)
    assert "Missing mandatory provenance sidecar" in str(exc_info.value)


def test_verify_project_assets_scans_broll_manifest(tmp_path: Path) -> None:
    """Verify verify_project_assets correctly scans and validates broll manifest slides."""
    proj_dir = tmp_path / "proj_broll"
    proj_dir.mkdir(parents=True, exist_ok=True)

    img_p = _create_dummy_png(proj_dir / "broll" / "official_slide.png")
    _create_sidecar(img_p, provenance=DocumentProvenance.LIVE, verified=True)

    manifest = {
        "slides": [
            {
                "type": "official_data",
                "image_path": str(img_p),
                "title": "Fed Total Assets",
            }
        ]
    }

    records = verify_project_assets(
        project_dir=proj_dir,
        broll_manifest=manifest,
        allow_synthetic=False,
    )
    assert len(records) == 1
    assert records[0].verified is True
