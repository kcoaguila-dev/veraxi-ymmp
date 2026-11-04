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
