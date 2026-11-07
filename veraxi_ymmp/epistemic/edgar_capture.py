"""
Official SEC EDGAR and Primary Authority Document Capture Adapter.

Implements OfficialDocumentCapturePort according to Clean Architecture.
Features:
- Safe environment variable retrieval for SEC_USER_AGENT (SEC Fair Access Policy compliant)
- Playwright-based headless browser navigation with DOM text search and fluorescent highlighter
- High-DPI (Retina 2x/4K) element clipping with context padding
- Authoritative SEC EDGAR metadata framing and citation stamping (Form, CIK, Accession)
- Offline synthetic fallback engine for CI, unit tests, and air-gapped environments
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from veraxi_ymmp.epistemic.asset_guard import write_provenance_metadata
from veraxi_ymmp.epistemic.citation_card import BadgeKind, CitationCardRenderer, load_card_font
from veraxi_ymmp.epistemic.facts import (
    DocumentCaptureResult,
    DocumentCaptureSpec,
    DocumentProvenance,
    DocumentSourceType,
    ProvenanceRecord,
)
from veraxi_ymmp.core.logging import logger
from veraxi_ymmp.epistemic.web_capture import HtmlHighlightCapturer

DEFAULT_SEC_USER_AGENT = "VeraxiStudio-Research/1.0"


@dataclass(frozen=True)
class IxbrlFact:
    """Structured US-GAAP Inline XBRL fact extracted from SEC EDGAR filings."""
    value: float
    raw_text: str
    scale: float
    unit: str
    name: str
    context_ref: str
    decimals: int

def extract_ixbrl_facts(html_content: str) -> List[IxbrlFact]:
    """Extract machine-readable Inline XBRL facts from SEC EDGAR HTML."""
    if "ix:nonfraction" not in html_content.lower():
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    facts: List[IxbrlFact] = []
    for tag in soup.find_all(re.compile(r"^ix:nonfraction$", re.I)):
        raw_val = tag.get_text(strip=True).replace(",", "")
        try:
            val = float(raw_val)
        except ValueError:
            continue
        try:
            scale_power = int(tag.get("scale", 0))
        except (ValueError, TypeError):
            scale_power = 0
        scale = 10 ** scale_power
        dec_str = str(tag.get("decimals", "0")).strip().upper()
        decimals = 999 if dec_str == "INF" else (int(dec_str) if dec_str.lstrip("-").isdigit() else 0)
        facts.append(
            IxbrlFact(
                value=val * scale,
                raw_text=tag.get_text(strip=True),
                scale=float(scale),
                unit=tag.get("unitref", "usd").lower(),
                name=tag.get("name", ""),
                context_ref=tag.get("contextref", ""),
                decimals=decimals,
            )
        )
    return facts

@dataclass(frozen=True)
class SecParams:
    """SEC-specific capture parameters extracted from source_params."""

    form: str = "10-Q"
    accession_number: str = ""
    company_name: str = ""
    filing_date: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SecParams:
        return cls(
            form=str(data.get("form", "10-Q")),
            accession_number=str(data.get("accession_number", "")),
            company_name=str(data.get("company_name", "")),
            filing_date=str(data.get("filing_date", "")),
        )

# Well-known CIK and company registry for rapid resolution
WELL_KNOWN_COMPANIES: Dict[str, Tuple[str, str]] = {
    "MSFT": ("0000789019", "MICROSOFT CORPORATION"),
    "AAPL": ("0000320193", "APPLE INC"),
    "NVDA": ("0001045810", "NVIDIA CORPORATION"),
    "AMZN": ("0001018724", "AMAZON COM INC"),
    "GOOGL": ("0001652044", "ALPHABET INC"),
    "META": ("0001326801", "META PLATFORMS, INC."),
    "TSLA": ("0001318605", "TESLA, INC."),
}


def get_sec_user_agent(strict: bool = False) -> str:
    """
    Safely retrieve SEC User-Agent from environment variable.
    SEC EDGAR Fair Access policy requires User-Agent in 'Sample Company AdminContact@<sample company domain>.com' format.
    """
    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if not ua or ua == DEFAULT_SEC_USER_AGENT or "@" not in ua:
        if strict:
            raise ValueError(
                "SEC EDGAR Fair Access policy requires a valid User-Agent with contact email. "
                "Set environment variable SEC_USER_AGENT='SampleApp ContactEmail@domain.com'."
            )
        if not ua:
            logger.warning(
                "SEC_USER_AGENT environment variable is not set. "
                "Using default research agent. Set SEC_USER_AGENT='YourApp contact@yourdomain.com' "
                "to fully comply with SEC EDGAR Fair Access Policy."
            )
            return DEFAULT_SEC_USER_AGENT
    return ua


def resolve_company_meta(identifier: str) -> Tuple[str, str]:
    """Resolve ticker or identifier to (CIK, official company name)."""
    norm = identifier.strip().upper()
    if norm in WELL_KNOWN_COMPANIES:
        return WELL_KNOWN_COMPANIES[norm]
    if norm.isdigit():
        cik = norm.zfill(10)
        return (cik, f"CIK {cik}")
    return ("0000000000", norm)


_load_capture_font = load_card_font


class EdgarDocumentCaptureAdapter:
    """
    Adapter implementing OfficialDocumentCapturePort for SEC EDGAR and official filings.
    Supports Playwright headless browser capture and offline high-fidelity synthetic fallback.
    """

    def __init__(self, prefer_offline: bool = False) -> None:
        self.prefer_offline = prefer_offline
        self._capturer = HtmlHighlightCapturer()
        self._renderer = CitationCardRenderer()

    def is_available(self) -> bool:
        """Return True if capture adapter is ready (either Playwright or synthetic engine)."""
        return True

    def is_playwright_installed(self) -> bool:
        """Check whether Playwright package and browser are available."""
        return self._capturer.is_available()

    def capture_document(
        self,
        spec: DocumentCaptureSpec,
        output_path: Path,
    ) -> DocumentCaptureResult:
        """
        Capture document passage with highlighting and official metadata stamping.
        In live mode (prefer_offline=False), fails fast if Playwright is missing or the target is unreachable.
        In offline mode (prefer_offline=True), generates an explicitly labeled synthetic mock document.
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        sec_params = SecParams.from_dict(spec.source_params)
        cik, company_name = resolve_company_meta(spec.identifier)
        if sec_params.company_name:
            company_name = sec_params.company_name

        accession = sec_params.accession_number.strip()
        form = sec_params.form
        acc_display = f" | Accession: {accession}" if accession else ""
        citation = spec.citation_label or f"SEC EDGAR Form {form} | {company_name}{acc_display}"

        if not self.prefer_offline:
            if not spec.document_url:
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url="",
                    verified=False,
                    provenance=DocumentProvenance.LIVE,
                    error_message="document_url is required for live document capture.",
                )

            parsed = urlparse(spec.document_url)
            host = parsed.netloc.lower()
            is_sec_host = host == "sec.gov" or host.endswith(".sec.gov")
            if is_sec_host:
                try:
                    get_sec_user_agent(strict=True)
                except ValueError as err:
                    return DocumentCaptureResult(
                        success=False,
                        image_path=out_p,
                        citation_label=citation,
                        source_url=spec.document_url,
                        verified=False,
                        provenance=DocumentProvenance.LIVE,
                        error_message=str(err),
                    )

            if not self.is_playwright_installed():
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url=spec.document_url,
                    verified=False,
                    provenance=DocumentProvenance.LIVE,
                    error_message="Playwright is not installed or available for live capture.",
                )

            try:
                return self._capture_via_playwright(spec, out_p, cik, company_name, accession, form, citation)
            except Exception as exc:
                logger.warning(f"Playwright capture exception: {exc}")
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url=spec.document_url,
                    verified=False,
                    provenance=DocumentProvenance.LIVE,
                    error_message=f"Live capture failed: {exc}",
                )

        return self._render_synthetic_sec_document(
            spec=spec,
            out_path=out_p,
            cik=cik,
            company_name=company_name,
            accession=accession,
            form=form,
            citation_label=citation,
        )

    def _capture_via_playwright(
        self,
        spec: DocumentCaptureSpec,
        out_path: Path,
        cik: str,
        company_name: str,
        accession: str,
        form: str,
        citation_label: str,
    ) -> DocumentCaptureResult:
        """Execute browser-based DOM text search, highlighter injection, and high-DPI clipping via HtmlHighlightCapturer."""
        parsed = urlparse(spec.document_url)
        host = parsed.netloc.lower()
        is_sec_host = host == "sec.gov" or host.endswith(".sec.gov")
        is_live_https_sec = (parsed.scheme == "https") and is_sec_host

        user_agent = get_sec_user_agent(strict=is_live_https_sec)
        raw_clip_path = out_path.with_suffix(".raw.png")

        dom_result = self._capturer.capture_highlight(
            document_url=spec.document_url,
            target_text=spec.target_text,
            out_image_path=raw_clip_path,
            user_agent=user_agent,
            context_padding_px=spec.context_padding_px,
            highlight_color=spec.highlight_color or "#fef08a",
            device_scale_factor=spec.device_scale_factor,
        )

        if not dom_result.success:
            if raw_clip_path.is_file():
                raw_clip_path.unlink()
            return DocumentCaptureResult(
                success=False,
                image_path=out_path,
                citation_label=citation_label,
                source_url=spec.document_url,
                verified=False,
                provenance=DocumentProvenance.LIVE,
                error_message=dom_result.error_message,
            )

        parsed_final = urlparse(dom_result.final_url)
        final_host = parsed_final.netloc.lower()
        is_verified = (
            (parsed_final.scheme == "https")
            and (final_host == "sec.gov" or final_host.endswith(".sec.gov"))
            and dom_result.matched
        )

        badge_kind = BadgeKind.VERIFIED_PRIMARY if is_verified else BadgeKind.UNVERIFIED_SOURCE
        badge_override_text = "[SEC EDGAR VERIFIED PRIMARY SOURCE]" if is_verified else ""

        acc_text = (
            f"Official Accession No: {accession}  |  PRIMARY FILING EXCERPT"
            if accession
            else "PRIMARY FILING EXCERPT"
        )

        self._renderer.render_card(
            raw_image_path=raw_clip_path,
            out_path=out_path,
            agency_title="UNITED STATES SECURITIES AND EXCHANGE COMMISSION",
            header_meta=f"CIK: {cik}  |  EDGAR FORM {form}",
            entity_title=company_name,
            subtitle=acc_text,
            citation_label=citation_label,
            badge_kind=badge_kind,
            badge_override_text=badge_override_text,
        )

        if raw_clip_path.is_file():
            raw_clip_path.unlink()

        image_hash = hashlib.sha256(out_path.read_bytes()).hexdigest()
        sidecar_record = ProvenanceRecord(
            schema_version="1.0",
            image_path=str(out_path),
            image_sha256=image_hash,
            content_sha256=dom_result.content_sha256,
            source_type=DocumentSourceType.SEC_EDGAR,
            identifier=spec.identifier,
            citation_label=citation_label,
            source_url=spec.document_url,
            final_url=dom_result.final_url,
            http_status=200,
            verified=is_verified,
            provenance=DocumentProvenance.LIVE,
            retrieved_at=dom_result.retrieved_at,
            matched_text=dom_result.matched_text,
            metadata={
                "cik": cik,
                "company_name": company_name,
                "form": form,
                "accession_number": accession,
            },
        )
        sidecar_p = write_provenance_metadata(out_path, sidecar_record)

        return DocumentCaptureResult(
            success=True,
            image_path=out_path,
            citation_label=citation_label,
            source_url=spec.document_url,
            verified=is_verified,
            provenance=DocumentProvenance.LIVE,
            matched_text=dom_result.matched_text,
            metadata={
                "cik": cik,
                "company_name": company_name,
                "accession_number": accession,
                "engine": "playwright",
                "retrieved_at": dom_result.retrieved_at,
                "final_url": dom_result.final_url,
                "content_sha256": dom_result.content_sha256,
                "image_sha256": image_hash,
                "sidecar_path": str(sidecar_p),
            },
        )


    def _render_synthetic_sec_document(
        self,
        spec: DocumentCaptureSpec,
        out_path: Path,
        cik: str,
        company_name: str,
        accession: str,
        form: str,
        citation_label: str,
        width: int = 1200,
        height: int = 675,
    ) -> DocumentCaptureResult:
        """
        Synthesizes a high-fidelity, authoritative SEC 10-Q/10-K document card with highlighted passage.
        Guarantees 100% offline reliability for CI and automated tests.
        """
        img = Image.new("RGBA", (width, height), (248, 250, 252, 255))
        draw = ImageDraw.Draw(img)

        # Outer Frame
        draw.rectangle([0, 0, width - 1, height - 1], outline=(203, 213, 225, 255), width=2)

        # SEC Top Bar
        draw.rectangle([0, 0, width, 52], fill=(15, 23, 42, 255))
        f_bar_title = _load_capture_font(18, bold=True)
        f_bar_meta = _load_capture_font(15, bold=True)
        draw.text((28, 16), "UNITED STATES SECURITIES AND EXCHANGE COMMISSION", font=f_bar_title, fill=(241, 245, 249, 255))
        draw.text((width - 28, 17), f"CIK: {cik}  |  EDGAR FORM {form}", font=f_bar_meta, fill=(148, 163, 184, 255), anchor="ra")

        # Synthetic Test Fixture Watermark
        f_wm = _load_capture_font(26, bold=True)
        draw.text((width // 2, 85), "[SYNTHETIC TEST FIXTURE - NOT VERIFIED PROOF]", font=f_wm, fill=(220, 38, 38, 140), anchor="mm")

        # Document Header
        f_co = _load_capture_font(28, bold=True)
        draw.text((36, 68), company_name, font=f_co, fill=(15, 23, 42, 255))

        f_sub = _load_capture_font(16, bold=True)
        f_unit = _load_capture_font(15, bold=False)
        draw.text((36, 108), f"PART I. FINANCIAL STATEMENTS  |  FORM {form} AUDITED REPORT", font=f_sub, fill=(71, 85, 105, 255))
        draw.text((620, 109), "(Unaudited, in Millions of USD)", font=f_unit, fill=(100, 116, 139, 255))

        draw.line([(36, 138), (width - 36, 138)], fill=(203, 213, 225, 255), width=2)

        # Financial Line Items
        target_term = (spec.target_text or "Capital expenditures").strip()
        rows = [
            ("Net income attributable to common shareholders", "$ 22,036", "$ 20,081", False),
            ("Net cash provided by operating activities", "$ 34,200", "$ 29,400", False),
            (f"{target_term} (Cash outflows for additions)", "$ 17,500", "$ 9,920", True),
            ("Proceeds from issuance of common stock", "$ 1,250", "$ 1,180", False),
            ("Cash and cash equivalents at end of period", "$ 80,000", "$ 111,000", False),
        ]

        f_th = _load_capture_font(16, bold=True)
        draw.text((48, 150), "Statement Line Item", font=f_th, fill=(71, 85, 105, 255))
        draw.text((720, 150), "Current Period", font=f_th, fill=(71, 85, 105, 255), anchor="ra")
        draw.text((940, 150), "Prior Period", font=f_th, fill=(71, 85, 105, 255), anchor="ra")
        draw.text((1075, 150), "Status", font=f_th, fill=(71, 85, 105, 255), anchor="mm")
        draw.line([(36, 178), (width - 36, 178)], fill=(226, 232, 240, 255), width=1)

        start_y = 194
        row_h = 68
        f_row_en = _load_capture_font(20, bold=True)
        f_num_curr = _load_capture_font(24, bold=True)
        f_num_prior = _load_capture_font(22, bold=True)

        for i, (label, val1, val2, is_target) in enumerate(rows):
            ry = start_y + i * row_h
            mid_y = ry + (row_h - 10) // 2

            if is_target:
                draw.rounded_rectangle(
                    [36, ry - 3, width - 36, ry + row_h - 7],
                    radius=10,
                    fill=(254, 240, 138, 255),
                    outline=(202, 138, 4, 255),
                    width=3,
                )
                draw.text((52, mid_y), label, font=f_row_en, fill=(113, 63, 18, 255), anchor="lm")
                draw.text((720, mid_y), val1, font=f_num_curr, fill=(180, 83, 9, 255), anchor="rm")
                draw.text((940, mid_y), val2, font=f_num_prior, fill=(71, 85, 105, 255), anchor="rm")

                pill_x1, pill_x2 = 1000, 1150
                pill_y1, pill_y2 = mid_y - 15, mid_y + 15
                draw.rounded_rectangle([pill_x1, pill_y1, pill_x2, pill_y2], radius=8, fill=(202, 138, 4, 255))
                f_pill = _load_capture_font(12, bold=True)
                draw.text(((pill_x1 + pill_x2) // 2, mid_y), "MOCK CITED", font=f_pill, fill=(255, 255, 255, 255), anchor="mm")
            else:
                draw.text((52, mid_y), label, font=f_row_en, fill=(15, 23, 42, 255), anchor="lm")
                draw.text((720, mid_y), val1, font=f_num_curr, fill=(15, 23, 42, 255), anchor="rm")
                draw.text((940, mid_y), val2, font=f_num_prior, fill=(100, 116, 139, 255), anchor="rm")

            draw.line([(36, ry + row_h - 4), (width - 36, ry + row_h - 4)], fill=(241, 245, 249, 255), width=1)

        # Bottom Official Footer
        draw.line([(36, height - 48), (width - 36, height - 48)], fill=(203, 213, 225, 255), width=1)
        f_foot = _load_capture_font(14, bold=False)
        f_stamp = _load_capture_font(13, bold=True)
        draw.text((36, height - 28), citation_label, font=f_foot, fill=(100, 116, 139, 255))
        draw.text((width - 36, height - 28), "[SYNTHETIC TEST FIXTURE - NOT VERIFIED]", font=f_stamp, fill=(220, 38, 38, 255), anchor="ra")

        img.save(out_path)
        logger.info(f"Generated official document clipping: {out_path}")

        image_hash = hashlib.sha256(out_path.read_bytes()).hexdigest()
        retrieved_time = datetime.now(timezone.utc).isoformat()
        final_url = spec.document_url or f"https://www.sec.gov/edgar/browse/?CIK={cik}"

        sidecar_record = ProvenanceRecord(
            schema_version="1.0",
            image_path=str(out_path),
            image_sha256=image_hash,
            content_sha256=hashlib.sha256(b"SYNTHETIC_MOCK_SEC_DOCUMENT").hexdigest(),
            source_type=DocumentSourceType.SEC_EDGAR,
            identifier=spec.identifier,
            citation_label=citation_label,
            source_url=final_url,
            final_url=final_url,
            http_status=200,
            verified=False,
            provenance=DocumentProvenance.SYNTHETIC,
            retrieved_at=retrieved_time,
            matched_text=target_term,
            metadata={
                "cik": cik,
                "company_name": company_name,
                "accession_number": accession,
                "form": form,
                "engine": "synthetic_canvas",
            },
        )
        sidecar_p = write_provenance_metadata(out_path, sidecar_record)

        return DocumentCaptureResult(
            success=True,
            image_path=out_path,
            citation_label=citation_label,
            source_url=final_url,
            verified=False,
            provenance=DocumentProvenance.SYNTHETIC,
            matched_text=target_term,
            metadata={
                "cik": cik,
                "company_name": company_name,
                "accession_number": accession,
                "engine": "synthetic_canvas",
                "retrieved_at": retrieved_time,
                "image_sha256": image_hash,
                "sidecar_path": str(sidecar_p),
            },
        )
