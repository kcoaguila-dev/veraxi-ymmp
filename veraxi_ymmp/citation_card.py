"""
Authoritative 16:9 Citation Card Renderer.

Renders high-fidelity dark-slate canvas framing for captured official primary source
documents, financial disclosures, and statistical evidence.
Enforces typed BadgeKind invariants to ensure synthetic fixtures can never claim verification.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

from .facts import DocumentProvenance
from .logging import logger


class BadgeKind(str, Enum):
    """Authoritative badge type displayed on a citation card."""

    VERIFIED_PRIMARY = "verified_primary"
    UNVERIFIED_SOURCE = "unverified_source"
    SYNTHETIC_MOCK = "synthetic_mock"


def resolve_badge_kind(verified: bool, provenance: DocumentProvenance) -> BadgeKind:
    """
    Pure mapping function resolving the authoritative badge kind.
    Guardrail Invariant: A synthetic document can NEVER produce a verified badge.
    """
    if provenance == DocumentProvenance.SYNTHETIC:
        return BadgeKind.SYNTHETIC_MOCK
    if verified:
        return BadgeKind.VERIFIED_PRIMARY
    return BadgeKind.UNVERIFIED_SOURCE


BADGE_CONFIGS: Dict[BadgeKind, Tuple[str, Tuple[int, int, int, int]]] = {
    BadgeKind.VERIFIED_PRIMARY: ("[VERIFIED PRIMARY SOURCE]", (34, 197, 94, 255)),  # Emerald green
    BadgeKind.UNVERIFIED_SOURCE: ("[OFFICIAL CITATION - UNVERIFIED HOST]", (148, 163, 184, 255)),  # Slate
    BadgeKind.SYNTHETIC_MOCK: ("[SYNTHETIC TEST FIXTURE - NOT VERIFIED]", (220, 38, 38, 255)),  # Crimson
}


def load_card_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Safe font loader for capture canvas typography."""
    font_files = [
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "BIZ-UDGothicB.ttc" if bold else "BIZ-UDGothicR.ttc",
        "tahomabd.ttf" if bold else "tahoma.ttf",
    ]
    for ff in font_files:
        try:
            return ImageFont.truetype(ff, size)
        except Exception:
            continue
    return ImageFont.load_default()


class CitationCardRenderer:
    """Renders 16:9 authoritative citation cards for official primary authority documents."""

    def __init__(self, default_width: int = 1200, default_height: int = 675) -> None:
        self.width = default_width
        self.height = default_height

    def render_card(
        self,
        raw_image_path: Path,
        out_path: Path,
        agency_title: str,
        header_meta: str,
        entity_title: str,
        subtitle: str,
        citation_label: str,
        badge_kind: BadgeKind,
        badge_override_text: str = "",
    ) -> Path:
        """Frame a captured document screenshot inside an authoritative 16:9 citation card."""
        canvas = Image.new("RGBA", (self.width, self.height), (15, 23, 42, 255))
        draw = ImageDraw.Draw(canvas)

        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=(51, 65, 85, 255), width=2)

        # Top Bar: Agency / Source Header
        draw.rectangle([0, 0, self.width, 52], fill=(30, 41, 59, 255))
        f_top_l = load_card_font(18, bold=True)
        f_top_r = load_card_font(15, bold=True)
        draw.text((24, 15), agency_title, font=f_top_l, fill=(241, 245, 249, 255))
        draw.text((self.width - 24, 16), header_meta, font=f_top_r, fill=(251, 191, 36, 255), anchor="ra")

        # Entity Title Bar
        f_co = load_card_font(24, bold=True)
        f_acc = load_card_font(14, bold=False)
        draw.text((28, 68), entity_title, font=f_co, fill=(248, 250, 252, 255))
        draw.text((28, 102), subtitle, font=f_acc, fill=(148, 163, 184, 255))

        # Paste captured snippet in inner viewport
        inner_x1, inner_y1 = 28, 130
        inner_w, inner_h = self.width - 56, self.height - 190

        if raw_image_path.is_file():
            with Image.open(raw_image_path) as raw_img:
                raw_rgb = raw_img.convert("RGBA")
                raw_rgb.thumbnail((inner_w, inner_h), Image.Resampling.LANCZOS)
                px = inner_x1 + (inner_w - raw_rgb.width) // 2
                py = inner_y1 + (inner_h - raw_rgb.height) // 2
                canvas.paste(raw_rgb, (px, py), raw_rgb)

        # Bottom Bar: Authoritative Citation & Badge
        draw.line([(24, self.height - 50), (self.width - 24, self.height - 50)], fill=(51, 65, 85, 255), width=1)
        f_foot = load_card_font(14, bold=False)
        f_badge = load_card_font(13, bold=True)
        draw.text((28, self.height - 32), citation_label, font=f_foot, fill=(148, 163, 184, 255))

        default_badge_text, badge_color = BADGE_CONFIGS[badge_kind]
        badge_text = badge_override_text or default_badge_text
        draw.text((self.width - 28, self.height - 32), badge_text, font=f_badge, fill=badge_color, anchor="ra")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path)
        logger.info(f"Rendered authoritative citation card: {out_path}")
        return out_path


    def render_metric_card(
        self,
        out_path: Path,
        agency_title: str,
        header_meta: str,
        entity_title: str,
        subtitle: str,
        observation_value: str,
        observation_date: str,
        citation_label: str,
        badge_kind: BadgeKind,
        badge_override_text: str = "",
        is_mock: bool = False,
    ) -> Path:
        """Render 16:9 dark slate statistical evidence card canvas for macroeconomic series."""
        canvas = Image.new("RGBA", (self.width, self.height), (15, 23, 42, 255))
        draw = ImageDraw.Draw(canvas)

        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=(51, 65, 85, 255), width=2)

        # Top Bar: Header
        draw.rectangle([0, 0, self.width, 52], fill=(30, 41, 59, 255))
        f_top_l = load_card_font(18, bold=True)
        f_top_r = load_card_font(15, bold=True)
        draw.text((24, 15), agency_title, font=f_top_l, fill=(241, 245, 249, 255))
        draw.text((self.width - 24, 16), header_meta, font=f_top_r, fill=(251, 191, 36, 255), anchor="ra")

        if is_mock or badge_kind == BadgeKind.SYNTHETIC_MOCK:
            f_wm = load_card_font(26, bold=True)
            draw.text(
                (self.width // 2, 85),
                "[SYNTHETIC TEST FIXTURE - NOT VERIFIED PROOF]",
                font=f_wm,
                fill=(220, 38, 38, 140),
                anchor="mm",
            )

        # Entity / Series Title Bar
        f_title = load_card_font(22, bold=True)
        f_sub = load_card_font(15, bold=False)
        draw.text((28, 68), entity_title[:70], font=f_title, fill=(248, 250, 252, 255))
        draw.text((28, 102), subtitle, font=f_sub, fill=(148, 163, 184, 255))

        # Metric Display Viewport
        vp_x1, vp_y1 = 28, 135
        vp_w, vp_h = self.width - 56, self.height - 200
        draw.rounded_rectangle(
            [vp_x1, vp_y1, vp_x1 + vp_w, vp_y1 + vp_h],
            radius=12,
            fill=(30, 41, 59, 255),
            outline=(51, 65, 85, 255),
            width=2,
        )

        f_val_lbl = load_card_font(16, bold=True)
        f_val_num = load_card_font(52, bold=True)
        f_date_lbl = load_card_font(18, bold=False)

        draw.text((vp_x1 + 40, vp_y1 + 40), "LATEST OFFICIAL OBSERVATION", font=f_val_lbl, fill=(203, 213, 225, 255))
        draw.text((vp_x1 + 40, vp_y1 + 115), observation_value, font=f_val_num, fill=(250, 204, 21, 255))
        draw.text((vp_x1 + 40, vp_y1 + 185), f"Observation Date: {observation_date}", font=f_date_lbl, fill=(148, 163, 184, 255))

        # Bottom Bar: Authoritative Citation & Badge
        draw.line([(24, self.height - 50), (self.width - 24, self.height - 50)], fill=(51, 65, 85, 255), width=1)
        f_foot = load_card_font(14, bold=False)
        f_badge = load_card_font(13, bold=True)
        draw.text((28, self.height - 32), citation_label, font=f_foot, fill=(148, 163, 184, 255))

        default_badge_text, badge_color = BADGE_CONFIGS[badge_kind]
        badge_text = badge_override_text or default_badge_text
        draw.text((self.width - 28, self.height - 32), badge_text, font=f_badge, fill=badge_color, anchor="ra")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path)
        logger.info(f"Rendered authoritative metric citation card: {out_path}")
        return out_path

        return out_path
