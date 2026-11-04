#!/usr/bin/env python3
"""Asset setup, fixture provisioning, and SHA-256 tamper-evident integrity verification.

Ensures that:
1. Tracked official proof assets in `assets/official/` have tamper-evident sidecars
   and embedded PNG chunks. Unvouched legacy assets are marked verified=False,
   provenance=SYNTHETIC so the fail-closed pipeline guard prevents them from posing as live captures.
2. A default dark background stub exists in `assets/bg/default_dark.png` so fresh clones
   render cleanly without missing file errors.
3. Assets directory structure and gitignored BGM/background conventions are audited.

Usage:
    python scripts/setup_assets.py
    python scripts/setup_assets.py --verify-only
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from veraxi_ymmp.asset_guard import verify_image_asset, write_provenance_metadata  # noqa: E402
from veraxi_ymmp.facts import DocumentProvenance, DocumentSourceType, ProvenanceRecord  # noqa: E402


def get_official_asset_spec(filename: str) -> Tuple[DocumentSourceType, str, str]:
    stem = Path(filename).stem
    if "sec_" in stem:
        return (DocumentSourceType.SEC_EDGAR, stem.upper(), f"SEC Filing ({stem})")
    if "fred_" in stem:
        return (DocumentSourceType.FRED, stem.upper(), f"FRED Series ({stem})")
    if "cve_" in stem:
        return (DocumentSourceType.GOVERNMENT_STAT, stem.upper(), f"NVD Advisory ({stem})")
    return (DocumentSourceType.CUSTOM, stem, f"Primary Document ({stem})")


def setup_official_sidecars(official_dir: Path, verify_only: bool = False) -> Dict[str, Tuple[bool, bool]]:
    """
    Verify or provision sidecars for official assets.
    Returns mapping: filename -> (hash_valid, is_live_verified)
    """
    results: Dict[str, Tuple[bool, bool]] = {}
    if not official_dir.is_dir():
        return results

    for png_path in sorted(official_dir.glob("*.png")):
        sidecar = png_path.with_suffix(".meta.json")
        if not sidecar.is_file() and not verify_only:
            src_type, identifier, label = get_official_asset_spec(png_path.name)
            # Legacy unvouched assets default to verified=False, SYNTHETIC
            record = ProvenanceRecord(
                schema_version="1.0",
                image_path=png_path.relative_to(REPO_ROOT).as_posix(),
                image_sha256="",
                content_sha256="",
                source_type=src_type,
                identifier=identifier,
                citation_label=label,
                source_url="",
                final_url="",
                http_status=200,
                verified=False,
                provenance=DocumentProvenance.SYNTHETIC,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                metadata={"note": "Legacy procedural/PIL asset; requires capture command for live verification"},
            )
            write_provenance_metadata(png_path, record, embed_in_png=True)

        try:
            rec = verify_image_asset(png_path, allow_synthetic=True, require_sidecar=True)
            is_live = bool(rec and rec.verified and rec.provenance == DocumentProvenance.LIVE)
            results[png_path.name] = (True, is_live)
        except Exception as exc:
            results[png_path.name] = (False, False)
            print(f"❌ Failed verification for {png_path.name}: {exc}", file=sys.stderr)

    return results


def setup_default_background(bg_dir: Path, verify_only: bool = False) -> Path:
    bg_dir.mkdir(parents=True, exist_ok=True)
    default_bg = bg_dir / "default_dark.png"

    if not default_bg.is_file() and not verify_only:
        from PIL import Image

        img = Image.new("RGB", (1920, 1080), color=(15, 23, 42))
        img.save(default_bg, "PNG")

        record = ProvenanceRecord(
            schema_version="1.0",
            image_path=default_bg.relative_to(REPO_ROOT).as_posix(),
            image_sha256="",
            content_sha256="",
            source_type=DocumentSourceType.CUSTOM,
            identifier="DEFAULT_DARK_SLATE_BG",
            citation_label="Default Pro Dark Slate Canvas",
            source_url="",
            final_url="",
            http_status=200,
            verified=False,
            provenance=DocumentProvenance.SYNTHETIC,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
        write_provenance_metadata(default_bg, record, embed_in_png=True)

    return default_bg


def check_bgm_assets(bgm_dir: Path) -> int:
    bgm_dir.mkdir(parents=True, exist_ok=True)
    audio_files = [f for f in bgm_dir.iterdir() if f.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")]
    return len(audio_files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Veraxi YMMP Asset Provisioning & Integrity Setup")
    parser.add_argument("--verify-only", action="store_true", help="Only verify assets without creating missing sidecars")
    args = parser.parse_args()

    assets_dir = REPO_ROOT / "assets"
    official_dir = assets_dir / "official"
    bg_dir = assets_dir / "bg"
    bgm_dir = assets_dir / "bgm"

    print("🔍 Auditing veraxi-ymmp assets and SHA-256 tamper-evident records...")

    official_results = setup_official_sidecars(official_dir, verify_only=args.verify_only)
    passed_official = sum(1 for (ok, _) in official_results.values() if ok)
    live_official = sum(1 for (_, live) in official_results.values() if live)
    total_official = len(official_results)
    print(
        f"  • Official proof assets: {passed_official}/{total_official} verified via SHA-256 sidecars "
        f"({live_official} live, {passed_official - live_official} unverified/synthetic)."
    )

    default_bg = setup_default_background(bg_dir, verify_only=args.verify_only)
    bg_count = len(list(bg_dir.glob("*.*")))
    print(f"  • Background assets in assets/bg/: {bg_count} found (default: {default_bg.name}).")

    bgm_count = check_bgm_assets(bgm_dir)
    if bgm_count == 0:
        print("  ℹ️  No BGM tracks found in assets/bgm/. See assets/ASSETS.md for recommended royalty-free BGM.")
    else:
        print(f"  • BGM tracks in assets/bgm/: {bgm_count} found.")

    if total_official > 0 and passed_official < total_official:
        print("❌ Asset setup failed: Some official assets failed SHA-256 integrity verification.", file=sys.stderr)
        return 1

    print("✅ Asset guard and environment fixtures ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
