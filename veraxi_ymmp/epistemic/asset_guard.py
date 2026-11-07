"""
Authoritative Asset Provenance Guard.

Enforces fail-closed tamper-evident integrity checks and provenance tracking for
official primary authority evidence assets (SEC EDGAR, FRED, etc.).
Blocks synthetic mocks and unverified fixtures from leaking into production pipelines.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from veraxi_ymmp.epistemic.facts import DocumentProvenance, ProvenanceRecord
from veraxi_ymmp.core.logging import logger


class AssetIntegrityError(RuntimeError):
    """Raised when an asset fails tamper-evident integrity or provenance verification."""

    pass


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hexadecimal digest of a local file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_sidecar_path(image_path: Path) -> Optional[Path]:
    """
    Locate the provenance sidecar JSON file for a given image.
    Checks <name>.meta.json then <name>.<ext>.meta.json.
    """
    cand1 = image_path.with_suffix(".meta.json")
    if cand1.is_file():
        return cand1
    cand2 = Path(str(image_path) + ".meta.json")
    if cand2.is_file():
        return cand2
    return None


def write_provenance_metadata(
    image_path: Path,
    record: ProvenanceRecord,
    embed_in_png: bool = True,
) -> Path:
    """
    Authoritative helper to write sidecar (.meta.json) and embed provenance
    metadata directly into PNG tEXt chunks when applicable.

    Ensures that provenance travels inside the PNG itself even if sidecars are separated,
    and updates record.image_sha256 to reflect the final file bytes on disk.
    """
    image_path = Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Embed provenance into PNG chunk if image exists and is a PNG
    if embed_in_png and image_path.suffix.lower() == ".png" and image_path.is_file():
        try:
            from PIL import Image, PngImagePlugin

            with Image.open(image_path) as im:
                png_info = PngImagePlugin.PngInfo()
                for k, v in im.info.items():
                    if isinstance(k, str) and isinstance(v, str):
                        png_info.add_text(k, v)
                png_info.add_text("veraxi_provenance", record.provenance.value)
                png_info.add_text("veraxi_verified", "true" if record.verified else "false")
                png_info.add_text("veraxi_schema", record.schema_version)
                png_info.add_text("veraxi_identifier", record.identifier)
                # Save in place with embedded chunk
                im.save(image_path, pnginfo=png_info)
        except Exception as exc:
            logger.warning(f"Could not embed PNG metadata into {image_path}: {exc}")

    # 2. Recompute actual file sha256 to guarantee exact tamper-evident parity
    if image_path.is_file():
        record.image_sha256 = compute_file_sha256(image_path)

    # 3. Write sidecar JSON
    sidecar_path = image_path.with_suffix(".meta.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, indent=2)

    return sidecar_path


def verify_image_asset(
    image_path: Path,
    allow_synthetic: bool = False,
    require_sidecar: bool = False,
) -> Optional[ProvenanceRecord]:
    """
    Verify the tamper-evident integrity and provenance of a single image asset.

    Fail-closed policy:
    1. If require_sidecar is True, the sidecar MUST exist.
    2. If the asset is a PNG with embedded 'veraxi_provenance=synthetic' metadata,
       it MUST fail closed unless allow_synthetic is True, regardless of sidecar presence.
    3. If a sidecar exists:
       - Schema version must match '1.0'.
       - image_sha256 in the sidecar MUST match the actual file's SHA-256.
       - Unless allow_synthetic is True, provenance MUST NOT be SYNTHETIC and verified MUST be True.
    """
    if not image_path.is_file():
        raise AssetIntegrityError(f"Image asset file does not exist: {image_path}")

    # 1. Inspect embedded PNG metadata for synthetic tags
    if image_path.suffix.lower() == ".png":
        try:
            from PIL import Image

            with Image.open(image_path) as im:
                prov_tag = im.info.get("veraxi_provenance")
                verified_tag = im.info.get("veraxi_verified")

                if not allow_synthetic:
                    if prov_tag == DocumentProvenance.SYNTHETIC.value:
                        raise AssetIntegrityError(
                            f"Production pipeline blocked synthetic mock asset '{image_path}' "
                            f"(detected via embedded PNG metadata). "
                            f"Pass allow_synthetic=True for mock or testing runs."
                        )
                    if verified_tag == "false" and require_sidecar:
                        raise AssetIntegrityError(
                            f"Production pipeline blocked unverified asset '{image_path}' "
                            f"(detected via embedded PNG metadata)."
                        )
        except AssetIntegrityError:
            raise
        except Exception as exc:
            logger.debug(f"Could not inspect PNG metadata for {image_path}: {exc}")

    # 2. Sidecar inspection
    sidecar_path = find_sidecar_path(image_path)
    if not sidecar_path:
        if require_sidecar:
            raise AssetIntegrityError(
                f"Missing mandatory provenance sidecar (.meta.json) for official asset: {image_path}"
            )
        return None

    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as exc:
        raise AssetIntegrityError(
            f"Failed reading provenance sidecar {sidecar_path}: {exc}"
        ) from exc

    try:
        record = ProvenanceRecord.from_dict(raw_data)
    except Exception as exc:
        raise AssetIntegrityError(
            f"Invalid provenance sidecar schema in {sidecar_path}: {exc}"
        ) from exc

    actual_hash = compute_file_sha256(image_path)
    if actual_hash != record.image_sha256:
        raise AssetIntegrityError(
            f"Tampered asset detected! Image hash mismatch for {image_path}: "
            f"expected {record.image_sha256}, got {actual_hash}"
        )

    if not allow_synthetic:
        if record.provenance == DocumentProvenance.SYNTHETIC:
            raise AssetIntegrityError(
                f"Production pipeline blocked synthetic mock asset '{image_path}'. "
                f"Pass allow_synthetic=True for mock or testing runs."
            )
        if not record.verified:
            raise AssetIntegrityError(
                f"Production pipeline blocked unverified asset '{image_path}'. "
                f"Asset claims source {record.source_url} but verification failed."
            )

    return record


def verify_project_assets(
    project_dir: Path,
    script_entries: Optional[List[Dict[str, Any]]] = None,
    broll_manifest: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    allow_synthetic: bool = False,
) -> List[ProvenanceRecord]:
    """
    Scan and verify all assets in a project before pipeline compilation.
    Enforces fail-closed integrity for official assets and logs warnings if allow_synthetic is enabled.
    Fails closed if referenced assets do not exist on disk.
    """
    if allow_synthetic:
        logger.warning(
            "=" * 70 + "\n"
            "⚠️  WARNING: allow_synthetic is ENABLED.\n"
            "   Synthetic unverified mock assets are permitted for this pipeline run.\n"
            "   DO NOT deploy these artifacts to public production channels.\n"
            + "=" * 70
        )

    verified_records: List[ProvenanceRecord] = []

    # 1. Inspect broll_manifest
    if broll_manifest is not None:
        if isinstance(broll_manifest, dict):
            raw_slides = broll_manifest.get("slides") or broll_manifest.get("broll_manifest") or []
        elif isinstance(broll_manifest, list):
            raw_slides = broll_manifest
        else:
            raw_slides = []
        slides: List[Dict[str, Any]] = [s for s in raw_slides if isinstance(s, dict)]

        for slide in slides:
            stype = str(slide.get("type", "")).lower()
            img_val = slide.get("image_path") or slide.get("image") or slide.get("asset")
            if not img_val:
                continue

            is_official_slide = stype in ("official_data", "official_stat", "official_image")
            img_p = Path(img_val)
            if not img_p.is_absolute():
                resolved: Optional[Path] = None
                for base in [project_dir, project_dir / "broll", project_dir / "assets"]:
                    cand = base / img_p
                    if cand.is_file():
                        resolved = cand
                        break
                if resolved is None:
                    raise AssetIntegrityError(
                        f"Slide references non-existent asset: '{img_val}' in project '{project_dir}'"
                    )
                img_p = resolved
            elif not img_p.is_file():
                raise AssetIntegrityError(f"Slide references non-existent asset: '{img_p}'")

            is_official = is_official_slide or ("official" in str(img_p).lower())
            record = verify_image_asset(
                image_path=img_p,
                allow_synthetic=allow_synthetic,
                require_sidecar=is_official,
            )
            if record:
                verified_records.append(record)

    # 2. Inspect script entries
    if script_entries:
        for entry in script_entries:
            for key in ("image", "image_path", "bg", "asset"):
                val = entry.get(key)
                if not val:
                    continue
                val_str = str(val)
                img_p = Path(val_str)
                if not img_p.is_absolute():
                    resolved_script: Optional[Path] = None
                    for base in [
                        project_dir,
                        project_dir / "broll",
                        project_dir / "assets",
                        Path("artifacts/.user_uploaded"),
                        Path("artifacts"),
                        Path("assets"),
                    ]:
                        cand = base / img_p
                        if cand.is_file():
                            resolved_script = cand
                            break
                    if resolved_script is None:
                        raise AssetIntegrityError(
                            f"Script cut references non-existent asset: '{val_str}' in project '{project_dir}'"
                        )
                    img_p = resolved_script
                elif not img_p.is_file():
                    raise AssetIntegrityError(f"Script cut references non-existent asset: '{img_p}'")

                is_official = "official" in str(img_p).lower()
                record = verify_image_asset(
                    image_path=img_p,
                    allow_synthetic=allow_synthetic,
                    require_sidecar=is_official,
                )
                if record:
                    verified_records.append(record)

    # 3. Direct scan of project_dir/assets/official if present
    official_dir = project_dir / "assets" / "official"
    if official_dir.is_dir():
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            for doc_file in official_dir.glob(ext):
                record = verify_image_asset(
                    image_path=doc_file,
                    allow_synthetic=allow_synthetic,
                    require_sidecar=True,
                )
                if record:
                    verified_records.append(record)

    return verified_records
