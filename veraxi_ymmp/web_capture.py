"""
Reusable Web Document Capture & DOM Highlighting Infrastructure.

Provides Playwright headless browser navigation, DOM text search,
fluorescent highlighter injection, and high-DPI Retina clipping.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from .citation_card import BadgeKind, CitationCardRenderer, load_card_font
from .facts import (
    DocumentCaptureResult,
    DocumentCaptureSpec,
    DocumentProvenance,
    is_primary_authority_url,
)
from .logging import logger


@dataclass
class DOMHighlightResult:
    """Result of capturing and highlighting a DOM element."""

    success: bool
    raw_image_path: Path
    matched: bool
    matched_text: str
    error_message: str = ""
    retrieved_at: str = ""
    final_url: str = ""
    content_sha256: str = ""


class HtmlHighlightCapturer:
    """Playwright-based browser capturer with DOM search and highlighter injection."""

    def __init__(self) -> None:
        self._playwright_available: Optional[bool] = None

    def is_available(self) -> bool:
        """Return True if Playwright is installed and importable."""
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            import playwright.sync_api  # noqa: F401
            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
        return self._playwright_available

    def capture_highlight(
        self,
        document_url: str,
        target_text: str,
        out_image_path: Path,
        user_agent: str = "",
        context_padding_px: int = 40,
        highlight_color: str = "#fef08a",
        device_scale_factor: int = 2,
        timeout_ms: int = 30000,
    ) -> DOMHighlightResult:
        """
        Navigate to document_url, locate target_text in DOM, highlight with highlight_color,
        and save high-DPI clipped screenshot to out_image_path.
        """
        if not self.is_available():
            return DOMHighlightResult(
                success=False,
                raw_image_path=out_image_path,
                matched=False,
                matched_text="",
                error_message="Playwright is not installed or available.",
            )

        from playwright.sync_api import sync_playwright

        parsed = urlparse(document_url)
        is_local = parsed.scheme in ("", "file")
        target_uri = Path(document_url).resolve().as_uri() if is_local else document_url

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=user_agent or None,
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=device_scale_factor,
                )
                page = context.new_page()

                resp = page.goto(target_uri, wait_until="load", timeout=timeout_ms)
                if not is_local and (resp is None or resp.status >= 400):
                    browser.close()
                    status_str = str(resp.status) if resp else "no response"
                    return DOMHighlightResult(
                        success=False,
                        raw_image_path=out_image_path,
                        matched=False,
                        matched_text="",
                        error_message=f"HTTP request to {document_url} failed with status: {status_str}",
                    )

                trimmed_target = target_text.strip()
                js_script = """
                (args) => {
                    const targetText = args[0];
                    const highlightColor = args[1];
                    if (!targetText) return null;
                    const xpath = `//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '${targetText.toLowerCase()}')]`;
                    const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    let matchedEl = null;
                    for (let i = 0; i < result.snapshotLength; i++) {
                        const node = result.snapshotItem(i);
                        if (node && node.offsetParent !== null) {
                            matchedEl = node;
                            break;
                        }
                    }
                    if (!matchedEl) return null;

                    matchedEl.scrollIntoView({ behavior: 'instant', block: 'center' });
                    matchedEl.style.backgroundColor = highlightColor;
                    matchedEl.style.outline = '3px solid #ca8a04';
                    matchedEl.style.borderRadius = '4px';
                    matchedEl.style.boxShadow = '0 0 14px rgba(234, 179, 8, 0.45)';
                    matchedEl.style.color = '#0f172a';
                    matchedEl.style.fontWeight = 'bold';

                    const rect = matchedEl.getBoundingClientRect();
                    return {
                        x: window.scrollX + rect.left,
                        y: window.scrollY + rect.top,
                        width: rect.width,
                        height: rect.height,
                        text: matchedEl.innerText
                    };
                }
                """
                bbox = page.evaluate(js_script, [trimmed_target, highlight_color])

                if trimmed_target and (not bbox or bbox.get("width", 0) <= 0 or bbox.get("height", 0) <= 0):
                    browser.close()
                    return DOMHighlightResult(
                        success=False,
                        raw_image_path=out_image_path,
                        matched=False,
                        matched_text="",
                        error_message=f"Target text '{trimmed_target}' not found in document DOM",
                    )

                content_str = page.content()
                content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
                retrieved_time = datetime.now(timezone.utc).isoformat()
                final_url = page.url

                out_image_path.parent.mkdir(parents=True, exist_ok=True)
                if bbox and bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                    pad = context_padding_px
                    clip_x = max(0, bbox["x"] - pad)
                    clip_y = max(0, bbox["y"] - pad)
                    clip_w = min(1920, bbox["width"] + pad * 2)
                    clip_h = min(1080, bbox["height"] + pad * 2)

                    page.screenshot(
                        path=str(out_image_path),
                        clip={"x": clip_x, "y": clip_y, "width": clip_w, "height": clip_h},
                    )
                else:
                    page.screenshot(path=str(out_image_path))

                browser.close()

            return DOMHighlightResult(
                success=True,
                raw_image_path=out_image_path,
                matched=bool(bbox),
                matched_text=trimmed_target,
                retrieved_at=retrieved_time,
                final_url=final_url,
                content_sha256=content_hash,
            )
        except Exception as exc:
            logger.warning(f"HtmlHighlightCapturer error: {exc}")
            return DOMHighlightResult(
                success=False,
                raw_image_path=out_image_path,
                matched=False,
                matched_text="",
                error_message=str(exc),
            )




class WebDocumentCaptureAdapter:
    """
    Adapter implementing OfficialDocumentCapturePort for general web URLs & documentation.
    Supports Playwright DOM element highlighting and offline high-fidelity synthetic fallback.
    """

    def __init__(self, prefer_offline: bool = False) -> None:
        self.prefer_offline = prefer_offline
        self._capturer = HtmlHighlightCapturer()
        self._renderer = CitationCardRenderer()

    def is_available(self) -> bool:
        """Return True if capture adapter is ready (Playwright or synthetic fallback)."""
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
        Capture general web document passage with highlighting and authoritative framing.
        In live mode (prefer_offline=False), uses Playwright to capture and highlight the passage.
        In offline mode (prefer_offline=True), generates an explicitly labeled synthetic mock document.
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        url = spec.document_url or spec.identifier
        citation = spec.citation_label or (f"Web Source | {url}" if url else "Web Document Citation")

        if not self.prefer_offline:
            if not url:
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url="",
                    error_message="document_url or identifier must be provided for web capture",
                )
            if not self._capturer.is_available():
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url=url,
                    error_message="Playwright is not installed. Run 'pip install playwright && playwright install chromium'",
                )

            raw_tmp = out_p.with_suffix(".raw.png")
            dom_res = self._capturer.capture_highlight(
                document_url=url,
                target_text=spec.target_text,
                out_image_path=raw_tmp,
                context_padding_px=spec.context_padding_px,
                highlight_color=spec.highlight_color,
                device_scale_factor=spec.device_scale_factor,
            )
            if not dom_res.success:
                return DocumentCaptureResult(
                    success=False,
                    image_path=out_p,
                    citation_label=citation,
                    source_url=url,
                    error_message=dom_res.error_message,
                )

            verified = is_primary_authority_url(url, profile="general")
            badge_kind = BadgeKind.VERIFIED_PRIMARY if verified else BadgeKind.UNVERIFIED_SOURCE
            self._renderer.render_card(
                raw_image_path=raw_tmp,
                out_path=out_p,
                agency_title="WEB SOURCE DOCUMENT ARCHIVE",
                header_meta=url,
                entity_title=citation,
                subtitle="PRIMARY DOCUMENT PASSAGE",
                citation_label=citation,
                badge_kind=badge_kind,
            )
            if raw_tmp.exists():
                try:
                    raw_tmp.unlink()
                except Exception:
                    pass

            return DocumentCaptureResult(
                success=True,
                image_path=out_p,
                citation_label=citation,
                source_url=url,
                verified=verified,
                provenance=DocumentProvenance.LIVE,
                matched_text=dom_res.matched_text,
                metadata={
                    "content_sha256": dom_res.content_sha256,
                    "retrieved_at": dom_res.retrieved_at,
                    "final_url": dom_res.final_url,
                },
            )

        # Offline synthetic canvas fallback
        verified = is_primary_authority_url(url, profile="general") if url else False
        mock_raw = out_p.with_suffix(".mock.png")

        # Draw clean synthetic document excerpt
        mock_img = Image.new("RGBA", (1100, 480), (255, 255, 255, 255))
        d = ImageDraw.Draw(mock_img)
        f_title = load_card_font(24, bold=True)
        f_body = load_card_font(18, bold=False)
        f_highlight = load_card_font(20, bold=True)

        d.text((40, 40), citation, font=f_title, fill=(15, 23, 42, 255))
        d.line([(40, 80), (1060, 80)], fill=(226, 232, 240, 255), width=2)
        d.text((40, 110), "Primary document excerpt & highlighted citation:", font=f_body, fill=(71, 85, 105, 255))

        target_display = spec.target_text or "General web documentation excerpt"
        d.rounded_rectangle([40, 160, 1060, 240], radius=8, fill=(254, 240, 138, 255), outline=(202, 138, 4, 255), width=2)
        d.text((60, 185), f'"{target_display}"', font=f_highlight, fill=(113, 63, 18, 255))

        d.text((40, 280), f"Source URL: {url}", font=f_body, fill=(100, 116, 139, 255))
        mock_img.save(mock_raw)

        self._renderer.render_card(
            raw_image_path=mock_raw,
            out_path=out_p,
            agency_title="WEB SOURCE ARCHIVE",
            header_meta=url,
            entity_title=citation,
            subtitle="SYNTHETIC CITATION PREVIEW",
            citation_label=citation,
            badge_kind=BadgeKind.SYNTHETIC_MOCK,
        )
        if mock_raw.exists():
            try:
                mock_raw.unlink()
            except Exception:
                pass

        return DocumentCaptureResult(
            success=True,
            image_path=out_p,
            citation_label=citation,
            source_url=url,
            verified=False,
            provenance=DocumentProvenance.SYNTHETIC,
            matched_text=spec.target_text,
        )
