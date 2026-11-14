"""Project-level validation and staged-edit reconciliation gates."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from veraxi_ymmp.core.constants import (
    DEFAULT_BG_CANDIDATES,
    DEFAULT_BGM_CANDIDATES,
)
from veraxi_ymmp.core.script import validate_director_script

PayloadValidator = Callable[[Dict[str, Any]], List[str]]


def _collect_slide_texts(spec: Dict[str, Any]) -> List[str]:
    """Collect visible text elements from a broll_manifest entry for load checks."""
    skip_keys = {
        "type", "filename", "theme_color", "color", "is_vertical",
        "image_path", "image", "asset", "layout", "show_caption",
        "show_header", "show_citation", "advantage",
    }
    color_tokens = {"blue", "emerald", "amber", "purple", "rose", "red", "green", "violet", "left", "right"}
    texts: List[str] = []

    def _walk(val: Any) -> None:
        if isinstance(val, str):
            s = val.strip()
            if s and s.lower() not in color_tokens:
                texts.append(s)
        elif isinstance(val, (list, tuple)):
            for item in val:
                _walk(item)
        elif isinstance(val, dict):
            for k, sub_v in val.items():
                if k not in skip_keys and sub_v is not None:
                    _walk(sub_v)

    for k, v in spec.items():
        if k not in skip_keys and v is not None:
            _walk(v)
    return texts


def _asset_exists(raw_path: str, project_dir: Path, is_image: bool = False) -> bool:
    """Return True if *raw_path* exists in project/repo or is a known optional asset."""
    norm = raw_path.replace("\\", "/").strip()
    if is_image and norm in DEFAULT_BG_CANDIDATES:
        return True
    if not is_image and norm in DEFAULT_BGM_CANDIDATES:
        return True
    candidates = [
        project_dir / raw_path,
        project_dir / "assets" / raw_path,
        project_dir.parent.parent / raw_path,
        Path.cwd() / raw_path,
    ]
    if is_image:
        candidates.append(project_dir / "broll" / norm.removeprefix("broll/"))
    return any(p.is_file() for p in candidates)


def _validate_cuts_and_broll(
    payload: Dict[str, Any], project_dir: Path
) -> List[str]:
    """Validate visible cut lengths, unmapped ASCII tokens, assets, and slide load."""
    from veraxi_ymmp.audio.phonetics import find_unmapped_ascii_tokens, strip_phonetic_ruby
    from veraxi_ymmp.graphics.broll import MAX_SLIDE_CHARS, MAX_SLIDE_ELEMENTS, check_cognitive_load

    broll_specs = payload.get("broll_manifest", [])
    if not broll_specs and (project_dir / "broll_manifest.json").is_file():
        try:
            disk_broll = json.loads((project_dir / "broll_manifest.json").read_text(encoding="utf-8"))
            if isinstance(disk_broll, list):
                broll_specs = disk_broll
        except Exception:
            broll_specs = []
    declared_broll = {
        str(s.get("filename", "")).replace("\\", "/").removeprefix("broll/").strip()
        for s in broll_specs
        if isinstance(s, dict) and str(s.get("filename", "")).strip()
    }

    errors: List[str] = []
    for idx, entry in enumerate(payload.get("script", [])):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text", ""))
        char = str(entry.get("character", "unknown"))
        vis_len = len(strip_phonetic_ruby(text))
        if vis_len > 40:
            errors.append(f"Cut #{idx} ({char}): Exceeds 40 characters ({vis_len} chars).")
        unmapped = find_unmapped_ascii_tokens(text, project_dir=project_dir)
        if unmapped:
            errors.append(
                f"Cut #{idx} ({char}): Unmapped ASCII token(s) {unmapped}; "
                "use katakana or inline ruby '{Word|よみ}'."
            )
        img = entry.get("image")
        if img is not None and str(img).strip():
            img_raw = str(img).strip()
            img_norm = img_raw.replace("\\", "/").removeprefix("broll/").strip()
            if img_norm not in declared_broll and not _asset_exists(img_raw, project_dir, is_image=True):
                errors.append(
                    f"[ASSET] Cut #{idx} ({char}): image '{img_raw}' is not declared in "
                    "broll_manifest.json and does not exist on disk."
                )
        for akey in ("bgm", "sfx"):
            aval = entry.get(akey)
            if aval is not None and str(aval).strip() and not _asset_exists(str(aval).strip(), project_dir):
                errors.append(f"[ASSET] Cut #{idx} ({char}): {akey} '{str(aval).strip()}' does not exist on disk.")

    slide_limits = {
        "matrix": (200, 20), "architecture": (180, 20), "flow": (180, 20),
        "value_chain": (180, 20), "domino": (140, 20), "causality": (140, 20),
        "chain": (140, 20), "clash": (MAX_SLIDE_CHARS + 25, 16),
        "metric_clash": (MAX_SLIDE_CHARS + 25, 16),
    }
    for s_idx, spec in enumerate(payload.get("broll_manifest", [])):
        if not isinstance(spec, dict):
            errors.append(f"broll_manifest[{s_idx}] must be an object.")
            continue
        title = str(spec.get("title") or spec.get("filename") or f"slide_{s_idx}")
        max_c, max_e = slide_limits.get(
            str(spec.get("type", "metric")).lower(), (MAX_SLIDE_CHARS, MAX_SLIDE_ELEMENTS + 6)
        )
        try:
            check_cognitive_load(title, _collect_slide_texts(spec), max_chars=max_c, max_elements=max_e)
        except ValueError as exc:
            errors.append(f"[BROLL] {exc}")
    return errors


@contextlib.contextmanager
def _backup_project_state(resolved_dir: Path) -> Iterator[Dict[Path, bytes]]:
    """Snapshot mutable project artifacts & sources/ and restore them on exit."""
    sources_dir = resolved_dir / "sources"
    sources_existed = sources_dir.is_dir()
    pre_sources: Dict[Path, bytes] = {
        p: p.read_bytes() for p in (sources_dir.iterdir() if sources_existed else ()) if p.is_file()
    }
    tracked = ("script.json", "claims.json", "broll_manifest.json", "thumbnail_config.json", "sources.md")
    backups = [
        (resolved_dir / fn, (resolved_dir / fn).read_bytes() if (resolved_dir / fn).is_file() else None)
        for fn in tracked
    ]
    tmp_script = resolved_dir / ".candidate_script.tmp.json"
    try:
        yield pre_sources
    finally:
        tmp_script.unlink(missing_ok=True)
        for fpath, prev in reversed(backups):
            if prev is None:
                fpath.unlink(missing_ok=True)
            else:
                fpath.write_bytes(prev)
        if sources_dir.is_dir():
            for item in list(sources_dir.iterdir()):
                if item in pre_sources:
                    item.write_bytes(pre_sources[item])
                elif item.is_file():
                    item.unlink(missing_ok=True)
            if not sources_existed and not any(sources_dir.iterdir()):
                sources_dir.rmdir()


def _load_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _pacing_errors(script_entries: Sequence[Any]) -> List[str]:
    from veraxi_ymmp.editorial.pacing import audit_script_pacing

    report = audit_script_pacing(list(script_entries))
    if report.retention_score >= 80:
        return []
    msgs = [
        f"[PACING {v.rule_name}] {v.message} (Remedy: {v.remedy})"
        for v in report.violations
        if v.severity in {"ERROR", "WARNING"}
    ]
    return msgs or [f"[PACING] Retention score {report.retention_score}/100 is below 80."]


def _run_fact_gate_check(
    resolved_dir: Path,
    payload: Dict[str, Any],
    script_entries: Sequence[Any],
    evidence_markdown: Optional[str],
    manifest_data: Optional[Dict[str, Any]],
) -> List[str]:
    """Build or reconcile claims and run audit_project_facts with disk rollback."""
    from veraxi_ymmp.editorial.script_ingest import (
        ingest_notebooklm_markdown_to_claims,
        parse_markdown_evidence_table,
        reconcile_claims_for_edited_script,
    )
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
    from veraxi_ymmp.epistemic.facts import claims_to_json, load_claims

    ev_text = evidence_markdown
    if ev_text is None and (resolved_dir / "evidence.md").is_file():
        ev_text = (resolved_dir / "evidence.md").read_text(encoding="utf-8")
    claims_path = resolved_dir / "claims.json"
    sources_dir = resolved_dir / "sources"
    tmp_script = resolved_dir / ".candidate_script.tmp.json"

    with _backup_project_state(resolved_dir):
        existing_claims = load_claims(claims_path) if claims_path.is_file() else []
        has_ev_table = ev_text is not None and bool(parse_markdown_evidence_table(ev_text))
        if existing_claims or has_ev_table:
            mf = manifest_data if manifest_data is not None else _load_json_dict(sources_dir / "manifest.json")
            if existing_claims:
                claims = reconcile_claims_for_edited_script(
                    script_entries, existing_claims, evidence_markdown=ev_text, manifest=mf, sources_dir=sources_dir
                )
            else:
                claims = ingest_notebooklm_markdown_to_claims(
                    script_entries, ev_text or "", manifest=mf, sources_dir=sources_dir
                )
            claims_path.write_text(claims_to_json(claims), encoding="utf-8")
        if not claims_path.is_file():
            return []
        tmp_script.write_text(json.dumps(list(script_entries), indent=2, ensure_ascii=False), encoding="utf-8")
        for fname, key in (("broll_manifest.json", "broll_manifest"), ("thumbnail_config.json", "thumbnail_config")):
            if payload.get(key):
                (resolved_dir / fname).write_text(
                    json.dumps(payload[key], indent=2, ensure_ascii=False), encoding="utf-8"
                )
        outcome = audit_project_facts(tmp_script)
        return [
            f"[FACTS] {r.claim.id} (cut {r.claim.cut_index}) {r.verdict.value}: {r.reason}"
            for r in outcome.blockers
        ]


def _validate_cross_file_and_evidence_scale_parity(
    payload: Dict[str, Any],
    evidence_markdown: Optional[str],
    claims: Optional[Sequence[Any]] = None,
    pre_existing_mags: Optional[Sequence[float]] = None,
) -> List[str]:
    """Verify cross-file macro figure parity and 10x billion/億 scale conversions."""
    from veraxi_ymmp.epistemic.epistemic_units import (
        extract_scaled_magnitudes,
        extract_token_magnitudes,
    )

    errors: List[str] = []
    script_entries = payload.get("script", [])
    script_mags: List[float] = []
    for entry in script_entries:
        if isinstance(entry, dict):
            script_mags.extend(extract_scaled_magnitudes(str(entry.get("text", ""))))
    ev_mags = extract_scaled_magnitudes(evidence_markdown) if evidence_markdown else []
    claim_mags: List[float] = []
    for cl in claims or ():
        if getattr(cl, "evidence", None) or getattr(cl, "axiom", False):
            claim_mags.extend(extract_scaled_magnitudes(getattr(cl, "text", "")))
        if getattr(cl, "derivation", ""):
            claim_mags.extend(extract_scaled_magnitudes(cl.derivation))
        for ev in getattr(cl, "evidence", ()) or ():
            if getattr(ev, "quote", ""):
                claim_mags.extend(extract_scaled_magnitudes(ev.quote))
    pair_mags = [
        v for i, a in enumerate(script_mags) for b in script_mags[i + 1 :] for v in (a + b, abs(a - b))
    ]
    anchor_mags = script_mags + ev_mags + claim_mags + pair_mags + list(pre_existing_mags or ())

    if ev_mags:
        known_mags = ev_mags + claim_mags
        for idx, entry in enumerate(script_entries):
            if not isinstance(entry, dict):
                continue
            for tok, vals in extract_token_magnitudes(str(entry.get("text", ""))).items():
                m_vals = [v for v in vals if v >= 1e6]
                if not m_vals or any(
                    abs(mv - em) / max(mv, em, 1.0) < 0.05 for mv in m_vals for em in known_mags
                ):
                    continue
                off = next(
                    (
                        em for mv in m_vals for em in ev_mags
                        if em >= 1e6 and (
                            abs(mv * 10.0 - em) / max(em, 1.0) < 0.05
                            or abs(mv / 10.0 - em) / max(em, 1.0) < 0.05
                        )
                    ),
                    None,
                )
                if off is not None:
                    errors.append(
                        f"[SCALE] Cut #{idx}: Figure '{tok}' ({m_vals[0]:g}) is 10x off from "
                        f"evidence ({off:g}) — check billion/億 conversion ($1B = 10億ドル)."
                    )

    if anchor_mags:
        targets: List[Tuple[str, str]] = [
            (f"broll_manifest[{s_idx}]", " ".join(_collect_slide_texts(spec)))
            for s_idx, spec in enumerate(payload.get("broll_manifest", []))
            if isinstance(spec, dict)
        ]
        thumb = payload.get("thumbnail_config")
        if isinstance(thumb, dict):
            targets.append(("thumbnail_config", json.dumps(thumb, ensure_ascii=False)))
        for label, txt in targets:
            for tok, vals in extract_token_magnitudes(txt).items():
                m_vals = [v for v in vals if v >= 1e8]
                if m_vals and not any(
                    abs(mv - am) / max(mv, am, 1.0) < 0.05 for mv in m_vals for am in anchor_mags
                ):
                    errors.append(
                        f"[SCALE] {label} macro figure '{tok}' ({m_vals[0]:g}) "
                        "does not match any figure in script or evidence.md."
                    )
    return errors


def _lookup_staged_text(
    project_dir: Path, filename: str, staged_files: Dict[str, str], root: Optional[Path]
) -> Tuple[Optional[str], Optional[str]]:
    """Return (text, matched_prefix) for *filename* from staged_files or project_dir."""
    base_root = root.resolve() if root is not None else project_dir.resolve()
    target = (project_dir / filename).resolve()
    for key, val in staged_files.items():
        if key == filename:
            return val, ""
        if (base_root / key).resolve() == target:
            prefix = key[: -len(filename)] if key.endswith(filename) else ""
            return val, prefix
    disk_file = project_dir / filename
    return (disk_file.read_text(encoding="utf-8") if disk_file.is_file() else None), None


def _parse_staged_json(raw: Optional[str], expected: type, label: str) -> Tuple[Any, Optional[str]]:
    if raw is None:
        return None, None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"[SCHEMA] {label}: {exc}"
    if not isinstance(val, expected):
        return None, f"[SCHEMA] {label} must be a JSON {'array' if expected is list else 'object'}."
    return val, None


def validate_and_reconcile_staged_project(
    project_dir: Path,
    staged_files: Dict[str, str],
    root: Optional[Path] = None,
    strict_facts: bool = True,
) -> Tuple[Optional[str], List[str]]:
    """Validate staged project edits and reconcile claims.json before writing to disk."""
    from veraxi_ymmp.editorial.notebooklm_verify import promote_hook_and_thumbnail_central_claims
    from veraxi_ymmp.editorial.script_ingest import (
        parse_markdown_evidence_table,
        reconcile_claims_for_edited_script,
    )
    from veraxi_ymmp.epistemic.epistemic_units import extract_scaled_magnitudes
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
    from veraxi_ymmp.epistemic.facts import claims_from_json, claims_to_json

    resolved_dir = project_dir.resolve()
    script_raw, prefix = _lookup_staged_text(resolved_dir, "script.json", staged_files, root)
    if script_raw is None:
        return None, [f"[SCHEMA] {resolved_dir.name}/script.json not found."]
    try:
        script_entries = validate_director_script(json.loads(script_raw))
    except (json.JSONDecodeError, ValueError) as exc:
        return None, [f"[SCHEMA] script.json: {exc}"]

    broll_raw, b_pref = _lookup_staged_text(resolved_dir, "broll_manifest.json", staged_files, root)
    prefix = prefix or b_pref or (f"projects/{resolved_dir.name}/" if root is not None else "")
    broll_parsed, b_err = _parse_staged_json(broll_raw, list, "broll_manifest.json")
    if b_err:
        return None, [b_err]
    broll_data: List[Any] = broll_parsed or []

    thumb_raw, _ = _lookup_staged_text(resolved_dir, "thumbnail_config.json", staged_files, root)
    thumb_data, t_err = _parse_staged_json(thumb_raw, dict, "thumbnail_config.json")
    if t_err:
        return None, [t_err]

    ev_text, _ = _lookup_staged_text(resolved_dir, "evidence.md", staged_files, root)
    claims_raw, _ = _lookup_staged_text(resolved_dir, "claims.json", staged_files, root)
    existing_claims: List[Any] = []
    if claims_raw is not None:
        try:
            existing_claims = claims_from_json(claims_raw)
        except Exception as exc:
            return None, [f"[SCHEMA] claims.json: {exc}"]

    pre_mags: List[float] = []
    if (resolved_dir / "broll_manifest.json").is_file():
        try:
            disk_broll = json.loads((resolved_dir / "broll_manifest.json").read_text(encoding="utf-8"))
            if isinstance(disk_broll, list):
                for spec in broll_data:
                    if isinstance(spec, dict) and spec in disk_broll:
                        pre_mags.extend(extract_scaled_magnitudes(" ".join(_collect_slide_texts(spec))))
        except Exception:
            pass
    if thumb_data is not None and thumb_data == _load_json_dict(resolved_dir / "thumbnail_config.json"):
        pre_mags.extend(extract_scaled_magnitudes(json.dumps(thumb_data, ensure_ascii=False)))

    has_claims_or_ev = bool(claims_raw is not None or (ev_text and parse_markdown_evidence_table(ev_text)))
    sources_dir = resolved_dir / "sources"
    mf = _load_json_dict(sources_dir / "manifest.json")
    reconciled_claims_json: Optional[str] = None
    reconciled_claims: List[Any] = []
    errors: List[str] = []

    with _backup_project_state(resolved_dir) as pre_sources:
        if has_claims_or_ev:
            reconciled_claims = reconcile_claims_for_edited_script(
                script_entries, existing_claims, evidence_markdown=ev_text, manifest=mf, sources_dir=sources_dir
            )
            reconciled_claims = promote_hook_and_thumbnail_central_claims(reconciled_claims, script_entries, thumb_data)
            reconciled_claims_json = claims_to_json(reconciled_claims) + "\n"

        payload: Dict[str, Any] = {"script": script_entries, "broll_manifest": broll_data}
        if thumb_data is not None:
            payload["thumbnail_config"] = thumb_data
        errors.extend(_validate_cuts_and_broll(payload, resolved_dir))
        errors.extend(_validate_cross_file_and_evidence_scale_parity(
            payload, ev_text, claims=reconciled_claims, pre_existing_mags=pre_mags
        ))
        errors.extend(_pacing_errors(script_entries))

        if strict_facts and has_claims_or_ev and reconciled_claims_json is not None:
            (resolved_dir / "script.json").write_text(
                json.dumps(script_entries, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (resolved_dir / "claims.json").write_text(reconciled_claims_json, encoding="utf-8")
            if broll_raw is not None:
                (resolved_dir / "broll_manifest.json").write_text(broll_raw, encoding="utf-8")
            if thumb_raw is not None:
                (resolved_dir / "thumbnail_config.json").write_text(thumb_raw, encoding="utf-8")
            outcome = audit_project_facts(resolved_dir / "script.json")
            errors.extend(
                f"[FACTS] {r.claim.id} (cut {r.claim.cut_index}) {r.verdict.value}: {r.reason}"
                for r in outcome.blockers
            )
        if not errors and sources_dir.is_dir():
            for item in sources_dir.iterdir():
                if item.is_file() and pre_sources.get(item) != item.read_bytes():
                    staged_files[f"{prefix}sources/{item.name}"] = item.read_text(encoding="utf-8", errors="replace")
        return reconciled_claims_json, errors


def build_project_gate_validator(
    project_dir: Path,
    audit_pacing: bool = True,
    audit_facts: bool = True,
    evidence_markdown: Optional[str] = None,
    manifest_data: Optional[Dict[str, Any]] = None,
) -> PayloadValidator:
    """Build a validator enforcing retention pacing, slide load, and fact gates."""
    resolved_dir = project_dir.resolve()

    def _validate(payload: Dict[str, Any]) -> List[str]:
        errors = _validate_cuts_and_broll(payload, resolved_dir)
        script_entries = payload.get("script", [])
        ev_text = evidence_markdown
        if ev_text is None and (resolved_dir / "evidence.md").is_file():
            ev_text = (resolved_dir / "evidence.md").read_text(encoding="utf-8")
        errors.extend(_validate_cross_file_and_evidence_scale_parity(payload, ev_text))

        if audit_pacing:
            errors.extend(_pacing_errors(script_entries))

        if audit_facts:
            errors.extend(
                _run_fact_gate_check(
                    resolved_dir, payload, script_entries, evidence_markdown, manifest_data
                )
            )
        return errors

    return _validate
