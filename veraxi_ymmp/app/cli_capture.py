"""
CLI Command Handlers for Primary Authority Document Capture (Web, SEC EDGAR & FRED).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from veraxi_ymmp.epistemic.web_capture import get_default_document_registry
from veraxi_ymmp.epistemic.facts import DocumentCaptureSpec, DocumentSourceType


def cmd_capture(argv: list[str]) -> None:
    """Capture and highlight primary authority document proof (Web, PDF/HTML, Academic, SEC, FRED)."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp capture",
        description="Capture and highlight primary source document proof (Web, PDF/HTML, Academic, SEC, FRED).",
    )
    parser.add_argument(
        "--source",
        choices=["web", "sec", "sec_edgar", "fred"],
        default="web",
        help="Primary authority source (default: web)",
    )
    parser.add_argument(
        "--identifier",
        "-t",
        "--ticker",
        "--series",
        default="",
        help="Identifier: Ticker symbol (e.g. MSFT, NVDA) or FRED series ID (e.g. WALCL, FEDFUNDS)",
    )
    parser.add_argument("--form", "-f", default="10-Q", help="SEC Form type (default: 10-Q)")
    parser.add_argument(
        "--search",
        "--target",
        "-s",
        dest="target_text",
        default="",
        help="Text, figure, or line-item substring to locate and highlight",
    )
    parser.add_argument("--url", default="", help="Direct URL to filing or local HTML file")
    parser.add_argument("--accession", default="", help="SEC accession number (optional)")
    parser.add_argument("--company", default="", help="Full company name override")
    parser.add_argument("--title", default="", help="Economic series title override")
    parser.add_argument("--units", default="", help="Economic series units override")
    parser.add_argument("--out", "-o", default="", help="Output PNG path")
    parser.add_argument(
        "--mock",
        "--offline",
        action="store_true",
        help="Force offline high-fidelity synthetic canvas rendering",
    )

    args = parser.parse_args(argv)

    source_norm = args.source.lower()
    # Auto-detect source if --source was not explicitly specified:
    if "--source" not in argv:
        if any(t in argv for t in ("-t", "--ticker", "--accession", "--form")):
            source_norm = "sec"
        elif any(f in argv for f in ("--series", "--units")):
            source_norm = "fred"
        elif args.url:
            source_norm = "web"

    if source_norm in ("sec", "sec_edgar"):
        source_type = DocumentSourceType.SEC_EDGAR
        identifier = args.identifier or "MSFT"
        target_text = args.target_text or "Capital expenditures"
        out_path = Path(args.out or "assets/official/sec_cited_proof.png")
        source_params = {
            "form": args.form,
            "accession_number": args.accession,
            "company_name": args.company,
        }
    elif source_norm == "fred":
        source_type = DocumentSourceType.FRED
        identifier = args.identifier or "WALCL"
        target_text = args.target_text
        out_path = Path(args.out or "assets/official/fred_cited_proof.png")
        source_params = {
            "series_title": args.title,
            "units": args.units,
        }
    elif source_norm == "web":
        source_type = DocumentSourceType.WEB
        identifier = args.url or args.identifier
        target_text = args.target_text
        out_path = Path(args.out or "assets/official/web_cited_proof.png")
        source_params = {
            "title": args.title,
        }
    else:
        print(f"Unsupported document source: {args.source}", file=sys.stderr)
        sys.exit(1)

    spec = DocumentCaptureSpec(
        source_type=source_type,
        identifier=identifier,
        target_text=target_text,
        document_url=args.url,
        source_params=source_params,
    )

    registry = get_default_document_registry(prefer_offline=args.mock)
    adapter = registry.get(source_type)
    res = adapter.capture_document(spec, out_path)

    if res.success:
        print(f"Successfully generated official cited document: {res.image_path}")
        print(f"Citation: {res.citation_label}")
        print(f"Verified: {res.verified} (provenance: {res.provenance.value})")
    else:
        print(f"Error: {res.error_message}", file=sys.stderr)
        sys.exit(1)


def cmd_capture_sec(argv: list[str]) -> None:
    """Alias for 'capture --source sec'."""
    cmd_capture(["--source", "sec"] + argv)
