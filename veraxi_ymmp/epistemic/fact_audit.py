"""Application service: audit a project's claim ledger and write its source dossier."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import html
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
import urllib.request
import urllib.error
from bs4 import BeautifulSoup
from veraxi_ymmp.epistemic.dialectical import DialecticalAuditOutcome, audit_dialectical_balance
from veraxi_ymmp.epistemic.temporal_gate import audit_temporal_recency


from veraxi_ymmp.epistemic.fact_report import render_report
from veraxi_ymmp.epistemic.facts import (
    Claim,
    Evidence,
    ClaimKind,
    ClaimResult,
    ClaimWeight,
    EpistemicProfile,
    Stance,
    Verdict,
    canonical_institution,
    claims_to_json,
    compute_deterministic_grounding,
    enforce_source_tier,
    gate_failures,
    load_claims,
    verdict_for,
    verify_quote_in_source,
)

CLAIMS_FILENAME = "claims.json"
REPORT_FILENAME = "sources.md"

SOURCES_DIRNAME = "sources"


@dataclass
class StoredSource:
    text: str
    sha256: str
    url: str = ""
    manifest_sha_error: str = ""
    provenance: str = ""

    def __iter__(self) -> Any:
        yield self.text
        yield self.sha256
        yield self.url


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hexadecimal digest of a local file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_pdf_text(path: Path) -> str:
    """Extract clean text from a local PDF file, prefixing pages with [Page N]."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        pages_text: List[str] = []
        for i, page in enumerate(reader.pages):
            raw_text = page.extract_text() or ""
            norm_text = re.sub(r"\s+", " ", raw_text).strip()
            pages_text.append(f"[Page {i + 1}] {norm_text}")
        return "\n\n".join(pages_text)
    except Exception as ex:
        return f"[PDF extraction failed: {ex}]"


def load_project_sources(project_dir: Path) -> Dict[str, StoredSource]:
    """Load text, SHA-256 checksums, and URL metadata for files in projects/<project>/sources/.

    Supports:
    - Sidecar metadata: <source_id>.meta.json with {"url": "https://..."}
    - Manifest file: sources/manifest.json or sources/sources.json mapping source_id to {"url": ...}
    - Document frontmatter: line starting with 'URL: https://...' or '<!-- URL: https://... -->'
    """
    sources_dir = project_dir / SOURCES_DIRNAME
    if not sources_dir.is_dir():
        return {}

    manifest: Dict[str, Any] = {}
    for mf_name in ("manifest.json", "sources.json"):
        mf_path = sources_dir / mf_name
        if mf_path.is_file():
            try:
                manifest = json.loads(mf_path.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    out: Dict[str, StoredSource] = {}
    valid_exts = {".txt", ".md", ".json", ".html", ".htm", ".csv", ".pdf"}
    for p in sources_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in valid_exts or p.name.endswith(".meta.json"):
            continue
        if p.name in ("manifest.json", "sources.json"):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            digest = compute_file_sha256(p)
            source_url = ""

            # Check sidecar metadata <stem>.meta.json or <name>.meta.json
            provenance = ""
            meta_path = sources_dir / f"{p.stem}.meta.json"
            if not meta_path.is_file():
                meta_path = sources_dir / f"{p.name}.meta.json"
            if meta_path.is_file():
                try:
                    meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                    source_url = str(meta_data.get("url", "")).strip()
                    provenance = str(meta_data.get("provenance", "")).strip()
                except Exception:
                    pass

            manifest_sha_error = ""
            if manifest:
                entry = manifest.get(p.stem) or manifest.get(p.name) or {}
                if isinstance(entry, dict):
                    if not source_url:
                        source_url = str(entry.get("url", "")).strip()
                    if not provenance:
                        provenance = str(entry.get("provenance", "")).strip()
                    m_sha = str(entry.get("sha256", "")).strip()
                    if m_sha and m_sha.lower() != digest.lower():
                        manifest_sha_error = f"manifest.json sha256 ({m_sha[:8]}) does not match file on disk ({digest[:8]})"
                elif isinstance(entry, str) and not source_url:
                    source_url = entry.strip()

            # Check header / frontmatter (strictly 'URL:', not loose citations like 'Source:')
            if not source_url:
                first_lines = content[:500].splitlines()
                for line in first_lines[:3]:
                    m = re.match(r"^(?:<!--\s*)?URL:\s*(https?://\S+?)(?:\s*-->)?$", line.strip(), re.I)
                    if m:
                        source_url = m.group(1).strip()
                        break

            item = StoredSource(content, digest, source_url, manifest_sha_error=manifest_sha_error, provenance=provenance)
            out[p.stem] = item
            out[p.name] = item
        except Exception:
            continue
    return out




@dataclass
class FactAuditOutcome:
    results: List[ClaimResult]
    blockers: List[ClaimResult]
    report_path: Path
    dialectical: Optional[DialecticalAuditOutcome] = None

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


def clean_html_to_plain_text(html_text: str) -> str:
    """Extract clean text from HTML or plain-text response using BeautifulSoup, preserving JSON scripts."""
    if not html_text:
        return ""
    if "<" not in html_text or ">" not in html_text:
        return re.sub(r"\s+", " ", html_text).strip()
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        json_scripts = [sc.get_text(separator=" ", strip=True) for sc in soup.find_all("script", type="application/json") if sc.string or sc.get_text()]
        for tag in soup(["style", "svg", "noscript", "script"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        if json_scripts:
            text += " " + " ".join(json_scripts)
        text = html.unescape(text).replace('\"', '"').replace('\n', ' ')
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        clean = re.sub(r"<style[^>]*>.*?</style>", " ", html_text, flags=re.DOTALL | re.I)
        clean = re.sub(r"<script(?![^>]*application/json)[^>]*>.*?</script>", " ", clean, flags=re.DOTALL | re.I)
        clean = re.sub(r"<[^>]+>", " ", clean)
        return re.sub(r"\s+", " ", html.unescape(clean)).strip()


def verify_source_url_live(
    url: str,
    expected_quote: str = "",
    timeout: float = 15.0,
    cache: Optional[Dict[str, str]] = None,
    as_of: str = "",
    require_table_scale_in_body: bool = False,
) -> Tuple[bool, str]:
    """Perform a deterministic live reachability and content verification check on a source URL.

    Sends institutional/compliance-friendly User-Agent header (required by SEC EDGAR).
    Ensures HTTP 200, prevents open-redirect domain hopping, and checks for verbatim quote existence.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False, f"invalid or missing scheme in url '{url}'"

    if cache is not None and url in cache:
        decoded = cache[url]
        body_text = clean_html_to_plain_text(decoded)
    else:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "VeraxiYMMP/1.0 (epistemic-audit@veraxi.local)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                final_url = resp.geturl()
                if status != 200:
                    return False, f"HTTP {status} returned by origin"
                if canonical_institution(url) and canonical_institution(final_url) != canonical_institution(url):
                    return False, f"redirect host mismatch (requested {url}, redirected to {final_url})"
                raw = resp.read()
                if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    try:
                        import gzip
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                charset = resp.headers.get_content_charset() or "utf-8"
                decoded = raw.decode(charset, errors="replace")
                body_text = clean_html_to_plain_text(decoded)
                if cache is not None:
                    cache[url] = decoded
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, f"network error reaching URL: {e}"

    if as_of:
        from veraxi_ymmp.epistemic.facts import extract_timeseries_observation, verify_quote_in_source
        obs_date, obs_val = extract_timeseries_observation(body_text, as_of=as_of)
        if not obs_val:
            return False, f"no valid time series observation found for as_of='{as_of}' in '{url}'"
        if expected_quote:
            if not verify_quote_in_source(expected_quote, body_text) and not verify_quote_in_source(obs_val, expected_quote):
                return False, f"expected quote '{expected_quote}' does not match live observation {obs_date}:{obs_val} from '{url}'"
        return True, ""

    if expected_quote:
        from veraxi_ymmp.epistemic.facts import verify_quote_in_source
        if not verify_quote_in_source(expected_quote, body_text):
            return False, f"expected quote not found in live response body from '{url}'"
        if require_table_scale_in_body:
            has_scale = False
            raw_html_doc = decoded if "decoded" in locals() else body_text
            if raw_html_doc and "ix:nonfraction" in raw_html_doc.lower():
                from veraxi_ymmp.epistemic.edgar_capture import extract_ixbrl_facts
                for f in extract_ixbrl_facts(raw_html_doc):
                    if f.raw_text in expected_quote and f.scale == 1e6:
                        has_scale = True
                        break
            if not has_scale and "<table" in raw_html_doc.lower():
                try:
                    soup = BeautifulSoup(raw_html_doc, "html.parser")
                    for table in soup.find_all("table"):
                        t_text = table.get_text()
                        if expected_quote in t_text or any(w in t_text for w in expected_quote.split() if len(w) > 3):
                            prev = table.find_previous(["p", "div", "h1", "h2", "h3", "h4", "caption"])
                            cap = prev.get_text() if prev else ""
                            if "in millions" in (t_text[:500] + " " + cap).lower():
                                has_scale = True
                                break
                except Exception:
                    pass
            if not has_scale and "in millions" in body_text.lower():
                q_pos = body_text.find(expected_quote) if expected_quote else -1
                if q_pos >= 0:
                    local_win = body_text[max(0, q_pos - 600) : min(len(body_text), q_pos + len(expected_quote) + 200)]
                    if "in millions" in local_win.lower():
                        has_scale = True
                else:
                    has_scale = True
            if not has_scale:
                return False, f"table scale '(in millions)' required by quote not found in live response body from '{url}'"

    return True, ""


def audit_project_facts(
    script_path: Path,
    title: str = "",
    cut_times: Optional[Dict[int, float]] = None,
    profile: Optional[EpistemicProfile | str] = None,
    verify_urls: bool = False,
    adversarial: bool = False,
) -> FactAuditOutcome:
    """Read `claims.json` beside the script, verify quotes against sources/, write `sources.md`, return outcome.

    Raises FileNotFoundError when no ledger exists: a video with no ledger is unaudited.
    """
    project_dir = script_path.parent
    claims_path = project_dir / CLAIMS_FILENAME
    if not claims_path.is_file():
        raise FileNotFoundError(f"No claim ledger found: {claims_path}")

    # Resolve active epistemic profile
    if profile is None:
        for cfg_name in ("project.json", "config.json"):
            cfg_file = project_dir / cfg_name
            if cfg_file.is_file():
                try:
                    cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
                    p_val = cfg_data.get("epistemic_profile") or cfg_data.get("profile")
                    if p_val:
                        profile = p_val
                        break
                except Exception:
                    pass
    active_profile = EpistemicProfile(profile) if profile else EpistemicProfile.FINANCE

    script_data: Optional[List[Dict[str, Any]]] = None
    if script_path.is_file():
        try:
            raw_script = json.loads(script_path.read_text(encoding="utf-8-sig"))
            if isinstance(raw_script, list):
                script_data = raw_script
        except Exception:
            pass

    claims = load_claims(claims_path)
    sources = load_project_sources(project_dir)
    live_url_cache: Dict[str, str] = {}

    extra_domains: List[str] = []
    extra_aliases: Dict[str, Tuple[str, ...]] = {}
    sources_dir = project_dir / SOURCES_DIRNAME
    for mf_name in ("manifest.json", "sources.json"):
        mf_path = sources_dir / mf_name
        if mf_path.is_file():
            try:
                mf_data = json.loads(mf_path.read_text(encoding="utf-8"))
                if isinstance(mf_data.get("primary_domains"), list):
                    extra_domains = [str(d).strip() for d in mf_data["primary_domains"] if str(d).strip()]
                if isinstance(mf_data.get("entity_aliases"), dict):
                    extra_aliases = {k: tuple(v) for k, v in mf_data["entity_aliases"].items() if isinstance(v, list)}
                break
            except Exception:
                pass

    results: List[ClaimResult] = []
    for c in claims:
        quote_errors: List[str] = []
        for e in c.evidence:
            if not e.source_id:
                if c.weight is ClaimWeight.CENTRAL:
                    quote_errors.append(
                        f"central claim requires verified source in sources/, got unlinked '{e.url}'"
                    )
                elif bool(sources) and not e.manual:
                    quote_errors.append(
                        f"claim evidence '{e.url}' is not linked to any source in sources/ (set source_id or manual=true)"
                    )
                continue
            if e.source_id not in sources:
                quote_errors.append(f"source '{e.source_id}' not found in sources/")
                continue
            src = sources[e.source_id]
            src_text, src_sha, src_url = src.text, src.sha256, src.url

            # Central claims FAIL-CLOSED security checks:
            if c.weight is ClaimWeight.CENTRAL:
                if not src_url:
                    quote_errors.append(
                        f"central claim source '{e.source_id}' has no registered origin URL (requires manifest.json or .meta.json)"
                    )
                elif enforce_source_tier(src_url, 1, profile=active_profile, extra_primary_domains=extra_domains) != 1:
                    quote_errors.append(
                        f"central claim source '{e.source_id}' origin '{src_url}' is not a recognized Tier 1 primary authority"
                    )
                elif canonical_institution(e.url) != canonical_institution(src_url):
                    quote_errors.append(
                        f"source '{e.source_id}' registered for '{src_url}' ({canonical_institution(src_url)}), does not match evidence url '{e.url}' ({canonical_institution(e.url)})"
                    )

                from urllib.parse import urlparse
                parsed_src = urlparse(src_url)
                if "/searchedgar/" in parsed_src.path.lower() or parsed_src.path.rstrip("/") == "":
                    quote_errors.append(
                        f"central claim source '{e.source_id}' origin '{src_url}' is a generic search/index page, not a specific primary filing or series"
                    )
                if getattr(src, "provenance", "").lower() == "synthetic":
                    quote_errors.append(
                        f"central claim source '{e.source_id}' has synthetic provenance, which cannot be used for production audits"
                    )

                if not e.sha256:
                    quote_errors.append(
                        f"central claim evidence for source '{e.source_id}' is missing required sha256 checksum"
                    )
                elif e.sha256.lower() != src_sha.lower():
                    quote_errors.append(
                        f"tampered source '{e.source_id}' (expected sha256 {e.sha256[:8]}, got {src_sha[:8]})"
                    )
            else:
                # Non-central claims checks
                if e.sha256 and e.sha256.lower() != src_sha.lower():
                    quote_errors.append(
                        f"tampered source '{e.source_id}' (expected sha256 {e.sha256[:8]}, got {src_sha[:8]})"
                    )
                elif src_url and canonical_institution(e.url) != canonical_institution(src_url):
                    quote_errors.append(
                        f"source '{e.source_id}' registered for '{src_url}', does not match evidence url '{e.url}'"
                    )

            if src.manifest_sha_error:
                quote_errors.append(f"source '{e.source_id}': {src.manifest_sha_error}")
            if not verify_quote_in_source(e.quote, src_text):
                quote_errors.append(f"quote not found in stored source '{e.source_id}'")

        grounding_score: Optional[float] = None
        if not quote_errors and c.evidence:
            conf_quotes = [e.quote for e in c.evidence if e.stance is Stance.CONFIRMS and e.quote.strip()]
            if conf_quotes:
                ctx_parts = list(conf_quotes)
                for e in c.evidence:
                    if e.source_id and e.source_id in sources:
                        ctx_parts.append(sources[e.source_id].text[:400])
                merged_ctx = " ".join(ctx_parts)
                c_txt = c.text + (" " + c.derivation if c.derived and c.derivation else "")
                grounding_score = compute_deterministic_grounding(c_txt, merged_ctx, extra_aliases=extra_aliases)
                if grounding_score == 0.0 and script_data and 0 <= c.cut_index < len(script_data):
                    win_start = max(0, c.cut_index - 4)
                    discourse_cuts = [
                        str(entry.get("text", "")).strip()
                        for entry in script_data[win_start : c.cut_index + 1]
                        if isinstance(entry, dict) and "character" in entry
                    ]
                    discourse_text = " ".join(discourse_cuts)
                    grounding_score = compute_deterministic_grounding(discourse_text, merged_ctx, extra_aliases=extra_aliases)

                from veraxi_ymmp.epistemic.facts import NON_CHECKABLE_KINDS
                if grounding_score == 0.0 and c.kind not in NON_CHECKABLE_KINDS and not getattr(c, "axiom", False):
                    quote_errors.append("grounding check failed (0.0): claim text has zero lexical or entity overlap with quotes")

        # Optional live URL reachability and content verification:
        if verify_urls and c.evidence:
            for e in c.evidence:
                if e.url:
                    src_obj = sources.get(e.source_id) if e.source_id else None
                    req_scale = bool(src_obj and "in millions" in src_obj.text.lower())
                    is_live, err_msg = verify_source_url_live(
                        e.url,
                        expected_quote=e.quote if e.quote else "",
                        cache=live_url_cache,
                        as_of=getattr(e, "as_of", ""),
                        require_table_scale_in_body=req_scale,
                    )
                    if not is_live:
                        quote_errors.append(f"live URL verification failed for '{e.url}': {err_msg}")

        conf_src_texts = [sources[e.source_id].text for e in c.evidence if e.source_id and e.source_id in sources]
        res = verdict_for(c, quote_errors=quote_errors, profile=active_profile, source_texts=conf_src_texts, extra_primary_domains=extra_domains)
        if grounding_score is not None:
            res.grounding_score = grounding_score
        results.append(res)

    # Enforce at least one central claim on production scripts (len >= 15 with facts)
    if script_data is not None and len(script_data) >= 15:
        has_central = any(c.weight is ClaimWeight.CENTRAL for c in claims)
        has_checkables = any(c.kind not in (ClaimKind.OPINION, ClaimKind.COMMENTARY) for c in claims)
        if has_checkables and not has_central:
            dummy_claim = Claim(id="gate_central_missing", cut_index=0, text="Central thesis claim", kind=ClaimKind.FACT, weight=ClaimWeight.CENTRAL)
            results.append(ClaimResult(claim=dummy_claim, verdict=Verdict.UNVERIFIED, reason="production script ledger must designate at least one 'central' thesis claim backed by >=2 independent Tier-1 primary sources"))
        elif has_central:
            from veraxi_ymmp.epistemic.facts import extract_token_magnitudes, extract_scaled_magnitudes
            cent_mags: List[float] = []
            for cc in claims:
                if cc.weight is ClaimWeight.CENTRAL:
                    cent_mags.extend(extract_scaled_magnitudes(cc.text + (" " + cc.derivation if cc.derived and cc.derivation else "")))

            thumb_p = project_dir / "thumbnail_config.json"
            if thumb_p.is_file():
                try:
                    thumb_data = json.loads(thumb_p.read_text(encoding="utf-8"))
                    thumb_tok_mags = extract_token_magnitudes(json.dumps(thumb_data, ensure_ascii=False))
                    macro_vals = [v for vals in thumb_tok_mags.values() for v in vals if v >= 1e8]
                    if macro_vals:
                        for mv in macro_vals:
                            if not any(abs(mv - cm) / max(mv, cm, 1.0) < 0.05 for cm in cent_mags):
                                cl = Claim(id="gate_thumbnail_central_missing", cut_index=0, text=f"Thumbnail macro figure ({mv:g})", kind=ClaimKind.NUMBER, weight=ClaimWeight.CENTRAL)
                                results.append(ClaimResult(claim=cl, verdict=Verdict.UNVERIFIED, reason=f"thumbnail macro figure ({mv:g}) featured in thumbnail headline must be backed by at least one 'central' claim in claims.json", quote_errors=[f"thumbnail macro figure ({mv:g}) lacks corresponding central claim in ledger"]))
                except Exception:
                    pass

            # Check 2: Cold Open / Hook cuts (0..10) macro figures must map to central claims
            hook_macro_vals: List[Tuple[int, float, str]] = []
            for idx, entry in enumerate(script_data[:11]):
                if not isinstance(entry, dict) or "character" not in entry:
                    continue
                c_txt = str(entry.get("text", "")).strip()
                t_mags = extract_token_magnitudes(c_txt)
                for tok, vals in t_mags.items():
                    for v in vals:
                        if v >= 1e8:
                            hook_macro_vals.append((idx, v, tok))
            for h_idx, h_val, h_tok in hook_macro_vals:
                if not any(abs(h_val - cm) / max(h_val, cm, 1.0) < 0.05 for cm in cent_mags):
                    cl = Claim(id=f"gate_hook_central_missing_c{h_idx:02d}", cut_index=h_idx, text=f"Hook cut #{h_idx} macro figure '{h_tok}' ({h_val:g})", kind=ClaimKind.NUMBER, weight=ClaimWeight.CENTRAL)
                    results.append(ClaimResult(claim=cl, verdict=Verdict.UNVERIFIED, reason=f"macro figure '{h_tok}' ({h_val:g}) asserted in hook cut #{h_idx} must map to a verified 'central' claim in claims.json", quote_errors=[f"hook macro figure '{h_tok}' lacks corresponding central claim"]))

    # Script-to-ledger completeness check: ensure all numeric cuts in script.json are recorded
    if script_data is not None:
        recorded_cuts = {c.cut_index for c in claims}
        from veraxi_ymmp.epistemic.facts import (
            NON_CHECKABLE_KINDS,
            extract_claim_numbers,
            extract_scaled_magnitudes,
            extract_token_magnitudes,
        )
        for idx, entry in enumerate(script_data):
            if not isinstance(entry, dict) or "character" not in entry:
                continue
            cut_text = str(entry.get("text", "")).strip()
            is_num = classify_text(cut_text, strict_numbers=True) is ClaimKind.NUMBER
            if is_num and idx not in recorded_cuts:
                missing_claim = Claim(
                    id=f"missing_c{idx:02d}",
                    cut_index=idx,
                    text=cut_text,
                    kind=ClaimKind.NUMBER,
                    weight=ClaimWeight.MINOR,
                )
                results.append(
                    ClaimResult(
                        claim=missing_claim,
                        verdict=Verdict.UNVERIFIED,
                        reason="numeric dialogue cut in script.json is missing from claims.json (run draft-claims or classify as commentary)",
                    )
                )
            elif idx in recorded_cuts:
                matching_claim = next((cl for cl in claims if cl.cut_index == idx), None)
                if not matching_claim:
                    continue

                s_token_mags = extract_token_magnitudes(cut_text)
                s_nums = extract_claim_numbers(cut_text)
                has_concrete_financial_figure = bool(s_token_mags) or (
                    bool(s_nums)
                    and bool(re.search(r"[$¥€£%％倍]|ドル|円|(?:billion|million|trillion|thousand)|\d+\s*分の\s*\d+|半額|半分|倍増|半減", cut_text, re.I))
                )

                if has_concrete_financial_figure and (matching_claim.kind in NON_CHECKABLE_KINDS or getattr(matching_claim, "axiom", False)):
                    results.append(
                        ClaimResult(
                            claim=matching_claim,
                            verdict=Verdict.UNVERIFIED,
                            reason=f"cut #{idx} in script.json contains concrete quantitative figure(s) {s_nums} and cannot be bypassed as '{matching_claim.kind.value}' or axiom",
                            quote_errors=[f"quantitative dialogue cut #{idx} cannot be classified as non-checkable '{matching_claim.kind.value}' or axiom"],
                        )
                    )
                elif matching_claim.kind not in NON_CHECKABLE_KINDS and (is_num or bool(s_nums) or bool(s_token_mags)):
                    c_claim_text = matching_claim.text
                    if matching_claim.derived and matching_claim.derivation:
                        c_claim_text += " " + matching_claim.derivation
                    c_nums = extract_claim_numbers(c_claim_text)
                    c_mags = extract_scaled_magnitudes(c_claim_text)

                    missing_mags = []
                    for s_tok, s_vals in s_token_mags.items():
                        for sv in s_vals:
                            if not any(abs(sv - cv) / max(sv, cv, 1.0) < 0.05 for cv in c_mags):
                                missing_mags.append(f"{s_tok} ({sv:g})")

                    missing_nums = []
                    for sn in s_nums:
                        if sn not in s_token_mags and sn not in c_nums:
                            missing_nums.append(sn)

                    if missing_mags or missing_nums:
                        err_parts = missing_mags + missing_nums
                        if not c_nums and not c_mags:
                            reason_msg = f"cut #{idx} in script.json contains numbers {s_nums} but claims.json dropped all numeric values"
                        else:
                            reason_msg = f"cut #{idx} in script.json asserts number(s) {s_nums} which do not match claims.json ('{matching_claim.text}')"
                        results.append(
                            ClaimResult(
                                claim=matching_claim,
                                verdict=Verdict.UNVERIFIED,
                                reason=reason_msg,
                                quote_errors=[f"claim text missing numeric values present in script cut #{idx}: {err_parts}"],
                            )
                        )

    parity_blockers = audit_visual_and_metadata_parity(project_dir, claims, sources, results=results)
    results.extend(parity_blockers)

    dialectical_outcome = audit_dialectical_balance(claims, results, adversarial_mode=adversarial)
    for sif in dialectical_outcome.scope_inflation_issues:
        matching_claim = next((c for c in claims if c.id == sif.claim_id), None)
        if matching_claim:
            results.append(
                ClaimResult(
                    claim=matching_claim,
                    verdict=Verdict.UNVERIFIED,
                    reason=sif.message,
                    quote_errors=[sif.message],
                )
            )

    temporal_violations = audit_temporal_recency(claims)
    for tv in temporal_violations:
        matching_claim = next((c for c in claims if c.id == tv.claim_id), None)
        if matching_claim:
            results.append(
                ClaimResult(
                    claim=matching_claim,
                    verdict=Verdict.REFUTED if tv.severity == "ERROR" else Verdict.UNVERIFIED,
                    reason=tv.message,
                    quote_errors=[tv.message] if tv.severity == "ERROR" else [],
                )
            )

    report_path = project_dir / REPORT_FILENAME
    report_path.write_text(
        render_report(
            title or project_dir.name,
            results,
            cut_times=cut_times,
            live_verified=verify_urls,
            dialectical_outcome=dialectical_outcome,
        ),
        encoding="utf-8",
    )
    return FactAuditOutcome(results, gate_failures(results), report_path, dialectical=dialectical_outcome)


def draft_project_claims(
    script_path: Path,
    script: List[Dict[str, Any]],
    extract_qualitative: bool = False,
) -> Tuple[Path, int]:
    """Create or extend `claims.json` with draft claims; returns (path, number added)."""
    claims_path = script_path.parent / CLAIMS_FILENAME
    existing = load_claims(claims_path) if claims_path.is_file() else []
    merged = extract_draft_claims(script, existing, extract_qualitative=extract_qualitative)
    claims_path.write_text(claims_to_json(merged), encoding="utf-8")
    return claims_path, len(merged) - len(existing)


def audit_visual_and_metadata_parity(
    project_dir: Path,
    claims: Sequence[Claim],
    sources: Dict[str, StoredSource],
    results: Optional[Sequence[ClaimResult]] = None,
) -> List[ClaimResult]:
    """Verify that financial figures in broll_manifest, thumbnail_config, and youtube_metadata match claims.json."""
    from veraxi_ymmp.epistemic.facts import extract_token_magnitudes, extract_scaled_magnitudes, Claim, ClaimKind, ClaimWeight, Verdict, ClaimResult, eval_safe_arithmetic

    if results is not None:
        supported_claim_ids = {r.claim.id for r in results if r.verdict is Verdict.SUPPORTED and not r.quote_errors}
    else:
        from veraxi_ymmp.epistemic.facts import verdict_for
        supported_claim_ids = {c.id for c in claims if verdict_for(c).verdict is Verdict.SUPPORTED}

    approved_mags = []
    for c in claims:
        if c.id not in supported_claim_ids:
            continue
        c_text = c.text + (" " + c.derivation if c.derived and c.derivation else "")
        approved_mags.extend(extract_scaled_magnitudes(c_text))
        for e in c.evidence:
            if e.quote:
                approved_mags.extend(extract_scaled_magnitudes(e.quote))
        if c.derived and c.derivation:
            import re
            parts = re.split(r"\s*(?:=|≈|~|->|→|=>)\s*", c.derivation.strip(), maxsplit=1)
            lhs_val = eval_safe_arithmetic(parts[0])
            if lhs_val is not None:
                approved_mags.append(lhs_val)
            for sub_expr in re.findall(r"\([^)]+\)", c.derivation):
                sub_val = eval_safe_arithmetic(sub_expr)
                if sub_val is not None:
                    approved_mags.append(sub_val)

    blockers: List[ClaimResult] = []

    # 1. B-roll manifest
    broll_p = project_dir / "broll_manifest.json"
    if broll_p.is_file():
        try:
            broll_data = json.loads(broll_p.read_text(encoding="utf-8"))
            broll_text = json.dumps(broll_data, ensure_ascii=False)
            tok_mags = extract_token_magnitudes(broll_text)
            for tok, vals in tok_mags.items():
                for v in vals:
                    if v >= 1e8: # Only enforce major financial/macro figures (>= 1億 / $1M)
                        if not any(abs(v - av) / max(v, av, 1.0) < 0.05 for av in approved_mags):
                            cl = Claim(id="parity_broll_mismatch", cut_index=0, text=f"B-roll figure '{tok}' ({v:g})", kind=ClaimKind.NUMBER, weight=ClaimWeight.MINOR)
                            blockers.append(ClaimResult(claim=cl, verdict=Verdict.UNVERIFIED, reason=f"broll_manifest.json contains quantitative figure '{tok}' ({v:g}) which contradicts verified claims in claims.json"))
        except Exception:
            pass

    # 2. Thumbnail config
    thumb_p = project_dir / "thumbnail_config.json"
    if thumb_p.is_file():
        try:
            thumb_data = json.loads(thumb_p.read_text(encoding="utf-8"))
            thumb_text = json.dumps(thumb_data, ensure_ascii=False)
            tok_mags = extract_token_magnitudes(thumb_text)
            for tok, vals in tok_mags.items():
                for v in vals:
                    if v >= 1e8:
                        if not any(abs(v - av) / max(v, av, 1.0) < 0.05 for av in approved_mags):
                            cl = Claim(id="parity_thumbnail_mismatch", cut_index=0, text=f"Thumbnail figure '{tok}' ({v:g})", kind=ClaimKind.NUMBER, weight=ClaimWeight.MINOR)
                            blockers.append(ClaimResult(claim=cl, verdict=Verdict.UNVERIFIED, reason=f"thumbnail_config.json contains quantitative figure '{tok}' ({v:g}) which contradicts verified claims in claims.json"))
        except Exception:
            pass

    # 3. YouTube metadata
    for meta_name in ("youtube_metadata.json", "youtube_metadata.txt"):
        meta_p = project_dir / meta_name
        if meta_p.is_file():
            try:
                m_text = meta_p.read_text(encoding="utf-8", errors="replace")
                tok_mags = extract_token_magnitudes(m_text)
                for tok, vals in tok_mags.items():
                    for v in vals:
                        if v >= 1e8:
                            if not any(abs(v - av) / max(v, av, 1.0) < 0.05 for av in approved_mags):
                                cl = Claim(id=f"parity_{meta_name}_mismatch", cut_index=0, text=f"YouTube metadata figure '{tok}' ({v:g})", kind=ClaimKind.NUMBER, weight=ClaimWeight.MINOR)
                                blockers.append(ClaimResult(claim=cl, verdict=Verdict.UNVERIFIED, reason=f"{meta_name} contains quantitative figure '{tok}' ({v:g}) which contradicts verified claims in claims.json"))
            except Exception:
                pass

    return blockers


# --- Check-worthiness classification & claim drafting ---

_UNITS_PATTERN = r"\b(?:gw|mw|kw|tw|w|tb|gb|mb|kb|pb|nm|um|mm|km|ghz|mhz|khz|hz|kg|mg|ug|kcal|fps|bps|billion|million|trillion|thousand)\b"
_FACT_SIGNAL = re.compile(
    rf"[0-9０-９]|[億兆万]|[%％]|[$¥€£]|ドル|円|ユーロ|ポンド|年間|四半期|決算|シェア|倍|半額|半分|倍増|半減|\d+\s*分の\s*\d+|ギガワット|メガワット|テラバイト|ギガバイト|ナノメートル|{_UNITS_PATTERN}",
    re.I,
)
_REACTION_END = re.compile(r"[！？!?…]+$")
_MAX_REACTION_LEN = 12
_CONCRETE_NUM_PATT = re.compile(
    rf"[0-9０-９]+(?:\.[0-9０-９]+)?\s*(?:[億兆万%％倍$¥€£ドル円]|{_UNITS_PATTERN})|\d+\s*分の\s*\d+|半額|半分|倍増|半減",
    re.I,
)
_DECLARATIVE_JP_END = re.compile(r"(?:です|だ|である|ました|だった|となる|となった|と言われています|とされています)[。.]?$")
_DECLARATIVE_EN_END = re.compile(r"[a-zA-Z0-9)]\.$")


def classify_text(
    text: str,
    extract_qualitative: bool = False,
    strict_numbers: bool = False,
) -> ClaimKind | None:
    """Return the claim kind, or None when the cut contains nothing to fact-check."""
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) <= _MAX_REACTION_LEN and _REACTION_END.search(stripped):
        return ClaimKind.COMMENTARY
    if strict_numbers:
        if _CONCRETE_NUM_PATT.search(stripped):
            return ClaimKind.NUMBER
        return None
    if _FACT_SIGNAL.search(stripped):
        return ClaimKind.NUMBER
    if extract_qualitative and len(stripped) >= 10:
        if _DECLARATIVE_JP_END.search(stripped) or _DECLARATIVE_EN_END.search(stripped):
            return ClaimKind.FACT
    return None


def extract_draft_claims(
    script: Sequence[Dict[str, Any]],
    existing: Sequence[Claim] = (),
    extract_qualitative: bool = False,
    strict_numbers: bool = False,
) -> List[Claim]:
    """Draft claims for factual dialogue cuts, keeping any existing human-curated claims."""
    known = {(c.cut_index, c.text) for c in existing}
    next_id = len(existing) + 1
    drafts: List[Claim] = []
    for idx, entry in enumerate(script):
        text = entry.get("text")
        if not isinstance(text, str) or ("type" in entry and "character" not in entry):
            continue
        kind = classify_text(text, extract_qualitative=extract_qualitative, strict_numbers=strict_numbers)
        if kind not in (ClaimKind.NUMBER, ClaimKind.FACT) or (idx, text) in known:
            continue
        drafts.append(Claim(f"d{next_id:02d}", idx, text, kind, ClaimWeight.MINOR))
        next_id += 1
    return list(existing) + drafts

# --- Veraxi Proof Card & Grounding Helpers ---

_PASSAGES = re.compile(r"\((\d+)\s+passages?\s+retrieved\)")
_ROW = re.compile(r"^\|\s*(\d+)\s*\|(?P<doc>[^|]*)\|(?P<loc>[^|]*)\|(?P<quote>.*)\|\s*$")
_PAGE = re.compile(r"(?:p\.?|page)\s*(\d+)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s)\]>]+")


def parse_proof_card(card: str, tier: int = 2, retrieved_at: str = "") -> List[Evidence]:
    """Parse a proof card into confirming Evidence; returns [] for vacuous/empty cards."""
    m = _PASSAGES.search(card)
    if not m or int(m.group(1)) == 0:
        return []
    out: List[Evidence] = []
    for line in card.splitlines():
        row = _ROW.match(line.strip())
        if not row:
            continue
        quote = row.group("quote").strip().strip('*_"“”')
        if not quote:
            continue
        doc, loc = row.group("doc").strip(), row.group("loc").strip()
        url = _URL.search(doc) or _URL.search(loc)
        page = _PAGE.search(loc)
        out.append(
            Evidence(
                url=url.group(0) if url else doc,
                quote=quote,
                stance=Stance.CONFIRMS,
                tier=tier,
                page=int(page.group(1)) if page else None,
                retrieved_at=retrieved_at,
            )
        )
    return out


class ManualChecker:
    """FactChecker backed by a pre-collected evidence ledger (CI / reruns)."""

    def check(self, claim: Claim) -> List[Evidence]:
        return list(claim.evidence)


def evaluate_grounding_safe(
    claim_text: str,
    context_text: str,
    mcp_client: Any = None,
) -> float:
    """Safely evaluate grounding with Veraxi MCP if available, falling back to deterministic."""
    if mcp_client is not None:
        try:
            if hasattr(mcp_client, "evaluate_grounding"):
                res = mcp_client.evaluate_grounding(
                    context_text=context_text,
                    response_text=claim_text,
                )
                if isinstance(res, (int, float)):
                    return float(res)
        except Exception:
            pass
    return compute_deterministic_grounding(claim_text, context_text)
