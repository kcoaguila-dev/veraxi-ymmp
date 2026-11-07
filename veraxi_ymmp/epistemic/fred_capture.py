"""
Official Federal Reserve Economic Data (FRED) Primary Authority Capture Adapter.

Implements OfficialDocumentCapturePort according to Clean Architecture.
Features:
- Primary data ingestion from St. Louis Fed FRED series (e.g. WALCL, FEDFUNDS, CPIAUCSL)
- Public observation retrieval without scraping UI DOM
- Authoritative statistical evidence card generation (16:9 dark slate theme)
- Cryptographic SHA-256 audit trail and ISO UTC timestamp recording
- Offline synthetic fallback engine for CI and unit tests
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
from typing import Any, Dict, Tuple
import urllib.error
from urllib.parse import urlparse
import urllib.request

from veraxi_ymmp.epistemic.asset_guard import write_provenance_metadata
from veraxi_ymmp.epistemic.citation_card import BadgeKind, CitationCardRenderer
from veraxi_ymmp.epistemic.facts import (
    DocumentCaptureResult,
    DocumentCaptureSpec,
    DocumentProvenance,
    DocumentSourceType,
    ProvenanceRecord,
)
from veraxi_ymmp.core.logging import logger

DEFAULT_FRED_USER_AGENT = "VeraxiStudio-Research/1.0"


def get_fred_user_agent() -> str:
    """Safely retrieve FRED User-Agent from environment variable or clean default."""
    return (
        os.getenv("FRED_USER_AGENT", "").strip()
        or os.getenv("VERAXI_USER_AGENT", "").strip()
        or DEFAULT_FRED_USER_AGENT
    )


WELL_KNOWN_SERIES: Dict[str, Tuple[str, str, str]] = {
    "WALCL": ("Assets: Total Assets (Less Eliminations from Consolidation)", "Millions of U.S. Dollars", "Weekly"),
    "FEDFUNDS": ("Federal Funds Effective Rate", "Percent", "Monthly"),
    "CPIAUCSL": ("Consumer Price Index for All Urban Consumers: All Items", "Index 1982-1984=100", "Monthly"),
    "M2SL": ("M2 Money Supply", "Billions of U.S. Dollars", "Monthly"),
    "T10Y2Y": ("10-Year Treasury Constant Maturity Minus 2-Year Treasury", "Percent", "Daily"),
}


@dataclass(frozen=True)
class FredParams:
    """FRED-specific capture parameters extracted from source_params."""

    series_title: str = ""
    units: str = ""
    frequency: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FredParams:
        return cls(
            series_title=str(data.get("series_title", "")),
            units=str(data.get("units", "")),
            frequency=str(data.get("frequency", "")),
        )


class FredDocumentCaptureAdapter:
    """
    Adapter implementing OfficialDocumentCapturePort for St. Louis Fed FRED series.
    Renders high-fidelity statistical evidence cards citing primary data observations.
    """

    def __init__(self, prefer_offline: bool = False) -> None:
        self.prefer_offline = prefer_offline
        self._renderer = CitationCardRenderer()

    def is_available(self) -> bool:
        """Return True if FRED adapter is ready."""
        return True

    def capture_document(
        self,
        spec: DocumentCaptureSpec,
        output_path: Path,
    ) -> DocumentCaptureResult:
        """Capture FRED observation series and render authoritative evidence card."""
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        series_id = spec.identifier.strip().upper() or "WALCL"
        fred_params = FredParams.from_dict(spec.source_params)

        default_title, default_units, _ = WELL_KNOWN_SERIES.get(
            series_id, (f"FRED Series {series_id}", "Units", "Period")
        )
        title = fred_params.series_title or default_title
        units = fred_params.units or default_units

        series_url = spec.document_url or f"https://fred.stlouisfed.org/series/{series_id}"
        citation = spec.citation_label or f"St. Louis Fed FRED | Series: {series_id} | {title}"

        if not self.prefer_offline:
            try:
                return self._capture_live_fred(spec, out_p, series_id, title, units, series_url, citation)
            except Exception as exc:
                logger.warning(f"Live FRED capture exception: {exc}")
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url=series_url,
                    verified=False,
                    provenance=DocumentProvenance.LIVE,
                    error_message=f"Live FRED capture failed: {exc}",
                )

        return self._render_synthetic_fred_card(
            out_p=out_p,
            series_id=series_id,
            title=title,
            units=units,
            series_url=series_url,
            citation_label=citation,
            target_text=spec.target_text,
        )

    def _capture_live_fred(
        self,
        spec: DocumentCaptureSpec,
        out_p: Path,
        series_id: str,
        title: str,
        units: str,
        series_url: str,
        citation_label: str,
    ) -> DocumentCaptureResult:
        """Fetch live observation from St. Louis Fed public CSV feed."""
        csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        req = urllib.request.Request(
            csv_url,
            headers={"User-Agent": get_fred_user_agent()},
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content_bytes = resp.read()
                final_url = resp.geturl()
                http_status = int(getattr(resp, "status", getattr(resp, "code", 200)))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            return DocumentCaptureResult(
                success=False,
                image_path=out_p,
                citation_label=citation_label,
                source_url=series_url,
                verified=False,
                provenance=DocumentProvenance.LIVE,
                error_message=f"FRED live request failed: {exc}",
            )

        content_str = content_bytes.decode("utf-8", errors="replace")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        retrieved_time = datetime.now(timezone.utc).isoformat()

        # Parse CSV for latest valid observation
        reader = csv.reader(io.StringIO(content_str))
        rows = list(reader)
        if len(rows) < 2:
            return DocumentCaptureResult(
                success=False,
                image_path=out_p,
                citation_label=citation_label,
                source_url=series_url,
                verified=False,
                provenance=DocumentProvenance.LIVE,
                error_message=f"No observation rows returned for FRED series {series_id}",
            )

        latest_date, latest_val = "", ""
        for r in reversed(rows[1:]):
            if len(r) >= 2 and r[1] != ".":
                latest_date, latest_val = r[0], r[1]
                break

        # Dot-boundary check on final response URL to prevent evil-domain bypasses
        parsed_final = urlparse(final_url)
        final_host = parsed_final.netloc.lower()
        is_verified = (
            http_status == 200
            and (parsed_final.scheme == "https")
            and (final_host == "stlouisfed.org" or final_host.endswith(".stlouisfed.org"))
        )

        badge_kind = BadgeKind.VERIFIED_PRIMARY if is_verified else BadgeKind.UNVERIFIED_SOURCE
        badge_text = "[ST. LOUIS FED FRED VERIFIED PRIMARY SOURCE]" if is_verified else ""

        self._renderer.render_metric_card(
            out_path=out_p,
            agency_title="FEDERAL RESERVE BANK OF ST. LOUIS | FRED ECONOMIC DATA",
            header_meta=f"SERIES ID: {series_id}",
            entity_title=title,
            subtitle=f"Units: {units}  |  Official Primary Economic Series",
            observation_value=latest_val,
            observation_date=latest_date,
            citation_label=citation_label,
            badge_kind=badge_kind,
            badge_override_text=badge_text,
            is_mock=False,
        )

        image_hash = hashlib.sha256(out_p.read_bytes()).hexdigest()
        sidecar_record = ProvenanceRecord(
            schema_version="1.0",
            image_path=str(out_p),
            image_sha256=image_hash,
            content_sha256=content_hash,
            source_type=DocumentSourceType.FRED,
            identifier=series_id,
            citation_label=citation_label,
            source_url=series_url,
            final_url=final_url,
            http_status=http_status,
            verified=is_verified,
            provenance=DocumentProvenance.LIVE,
            retrieved_at=retrieved_time,
            matched_text=latest_val,
            metadata={
                "series_id": series_id,
                "observation_date": latest_date,
                "observation_value": latest_val,
                "engine": "fred_csv_live",
            },
        )
        sidecar_p = write_provenance_metadata(out_p, sidecar_record)

        return DocumentCaptureResult(
            success=True,
            image_path=out_p,
            citation_label=citation_label,
            source_url=series_url,
            verified=is_verified,
            provenance=DocumentProvenance.LIVE,
            matched_text=latest_val,
            metadata={
                "series_id": series_id,
                "observation_date": latest_date,
                "observation_value": latest_val,
                "engine": "fred_csv_live",
                "retrieved_at": retrieved_time,
                "final_url": final_url,
                "http_status": http_status,
                "content_sha256": content_hash,
                "image_sha256": image_hash,
                "sidecar_path": str(sidecar_p),
            },
        )

    def _render_synthetic_fred_card(
        self,
        out_p: Path,
        series_id: str,
        title: str,
        units: str,
        series_url: str,
        citation_label: str,
        target_text: str = "",
    ) -> DocumentCaptureResult:
        """Render offline mock FRED statistical evidence card with explicit synthetic watermark."""
        mock_val = target_text or "7,450,120"
        mock_date = "2024-10-01"

        self._renderer.render_metric_card(
            out_path=out_p,
            agency_title="FEDERAL RESERVE BANK OF ST. LOUIS | FRED ECONOMIC DATA",
            header_meta=f"SERIES ID: {series_id}",
            entity_title=title,
            subtitle=f"Units: {units}  |  Official Primary Economic Series",
            observation_value=mock_val,
            observation_date=mock_date,
            citation_label=citation_label,
            badge_kind=BadgeKind.SYNTHETIC_MOCK,
            badge_override_text="[SYNTHETIC TEST FIXTURE - NOT VERIFIED]",
            is_mock=True,
        )

        image_hash = hashlib.sha256(out_p.read_bytes()).hexdigest()
        retrieved_time = datetime.now(timezone.utc).isoformat()
        sidecar_record = ProvenanceRecord(
            schema_version="1.0",
            image_path=str(out_p),
            image_sha256=image_hash,
            content_sha256=hashlib.sha256(b"SYNTHETIC_MOCK_FRED_OBSERVATION").hexdigest(),
            source_type=DocumentSourceType.FRED,
            identifier=series_id,
            citation_label=citation_label,
            source_url=series_url,
            final_url=series_url,
            http_status=200,
            verified=False,
            provenance=DocumentProvenance.SYNTHETIC,
            retrieved_at=retrieved_time,
            matched_text=mock_val,
            metadata={
                "series_id": series_id,
                "observation_date": mock_date,
                "observation_value": mock_val,
                "engine": "synthetic_canvas",
            },
        )
        sidecar_p = write_provenance_metadata(out_p, sidecar_record)

        return DocumentCaptureResult(
            success=True,
            image_path=out_p,
            citation_label=citation_label,
            source_url=series_url,
            verified=False,
            provenance=DocumentProvenance.SYNTHETIC,
            matched_text=mock_val,
            metadata={
                "series_id": series_id,
                "observation_date": mock_date,
                "observation_value": mock_val,
                "engine": "synthetic_canvas",
                "retrieved_at": retrieved_time,
                "image_sha256": image_hash,
                "sidecar_path": str(sidecar_p),
            },
        )
