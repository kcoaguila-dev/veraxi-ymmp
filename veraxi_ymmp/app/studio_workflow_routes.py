"""Tier 3 Studio workflow routes for the 5-Step Golden Path (Steps 1, 2, 3, 5).

Wires the existing CLI/Tier 2 engines into the Studio REST API so the desktop
GUI reaches zero-CLI parity with the command line:

- Step 1: ``POST /api/ideate`` plus project source management
  (``GET|POST /api/projects/<name>/sources``), built on
  ``cli_ideate.generate_dossier_markdown`` / ``_write_script_seed``.
- Step 2: ``POST /api/projects/<name>/ingest``, built on
  ``editorial.script_ingest`` (evidence table + dialogue parsing).
- Step 3: ``POST /api/projects/<name>/validate``, built on
  ``editorial.pacing.audit_script_pacing`` and
  ``epistemic.fact_audit.draft_project_claims`` / ``audit_project_facts``.
- Step 5: ``POST /api/projects/<name>/qa``, built on ``cli_qa.run_project_qa``.

Verified signature notes (checked against main @ 8f8627e, see PR body):
``audit_project_facts`` takes a script *path* (not a project dir) and writes
``sources.md``; verdicts are the ``Verdict`` enum (``supported`` / ``refuted`` /
``unverified`` / ``opinion``), mapped here to the plan's
SUPPORTED / UNSUPPORTED / INSUFFICIENT labels while keeping the raw value.
``ingest_notebooklm_markdown_to_claims`` returns ``Claim`` objects; persisting
``claims.json`` is this module's job (via ``claims_to_json``).
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import json
import threading
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from veraxi_ymmp.app.cli_ideate import (
    ARCHETYPES,
    _slugify,
    _write_script_seed,
    generate_dossier_markdown,
)
from veraxi_ymmp.app.cli_qa import run_project_qa
from veraxi_ymmp.app.clip_ingest import (
    VIDEO_EXTENSIONS,
    ingest_clips,
    ingest_clips_from_manifest,
)
from veraxi_ymmp.core.utils import get_workspace_root
from veraxi_ymmp.epistemic.fact_audit import (
    audit_project_facts,
    compute_file_sha256,
    draft_project_claims,
)

_ALLOWED_SOURCE_EXTS = frozenset({".pdf", ".md", ".html", ".htm", ".txt"})
_MAX_SOURCE_BYTES = 25 * 1024 * 1024
_VERDICT_MAP = {
    "supported": "SUPPORTED",
    "refuted": "UNSUPPORTED",
    "unverified": "INSUFFICIENT",
    "opinion": "INSUFFICIENT",
}
_FRAME_LABELS = {
    "01_cold_open": "Cold Open",
    "02_first_slide": "First Slide",
    "03_guest_entrance": "Third Speaker",
    "04_mid_reaction": "Mid-Roll",
    "05_ending": "Ending",
}


def _project_dir(project_name: str) -> Path:
    """Resolve ``projects/<name>`` inside the workspace, rejecting traversal.

    The name check alone is not enough: ``projects/<name>`` itself could be a
    symlink or junction pointing outside the workspace, so the resolved path
    must stay inside the resolved projects root.
    """
    if ".." in project_name or "/" in project_name or "\\" in project_name:
        raise ValueError("Invalid project name")
    projects_root = (get_workspace_root() / "projects").resolve()
    proj_dir = (projects_root / project_name).resolve()
    if proj_dir.parent != projects_root:
        raise ValueError("Invalid project name")
    return proj_dir


def _contained_target(directory: Path, filename: str) -> Path:
    """Join ``filename`` onto ``directory``, rejecting symlink escapes."""
    target = (directory / filename).resolve()
    if target.parent != directory.resolve():
        raise ValueError(f"Path escapes its directory: {filename}")
    return target


def _load_json_file(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _load_script(proj_dir: Path) -> List[Dict[str, Any]]:
    raw = _load_json_file(proj_dir / "script.json", [])
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        for key in ("script", "cuts"):
            entries = raw.get(key)
            if isinstance(entries, list):
                return [e for e in entries if isinstance(e, dict)]
    return []


def _load_manifest(proj_dir: Path) -> Dict[str, Any]:
    manifest = _load_json_file(proj_dir / "sources" / "manifest.json", {})
    return manifest if isinstance(manifest, dict) else {}


def _sources_payload(proj_dir: Path) -> Dict[str, Any]:
    sources_dir = proj_dir / "sources"
    files: List[Dict[str, Any]] = []
    if sources_dir.is_dir():
        for fpath in sorted(sources_dir.iterdir()):
            if fpath.is_file() and fpath.name != "manifest.json":
                files.append(
                    {
                        "name": fpath.name,
                        "size": fpath.stat().st_size,
                        "sha256": compute_file_sha256(fpath),
                        "extension": fpath.suffix.lower(),
                    }
                )
    manifest = _load_manifest(proj_dir)
    return {"success": True, "sources": files, "sources_manifest": manifest}


def handle_ideate(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Step 1: create a project, NotebookLM dossier, seed, and sources manifest."""
    topic = str(body.get("topic", "")).strip()
    if not topic:
        return 400, {"success": False, "error": "topic is required"}
    archetype = str(body.get("archetype", "post_mortem")).strip() or "post_mortem"
    if archetype not in ARCHETYPES:
        return 400, {
            "success": False,
            "error": f"Unknown archetype '{archetype}'. Choices: {sorted(ARCHETYPES)}",
        }
    requested = str(body.get("project_name", "")).strip()
    slug = _slugify(requested) if requested else _slugify(topic)
    try:
        proj_dir = _project_dir(slug)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    existing_manifest = _load_manifest(proj_dir)
    if existing_manifest.get("topic") and existing_manifest["topic"] != topic:
        return 409, {
            "success": False,
            "error": (
                f"Project '{slug}' already exists for a different topic "
                f"('{existing_manifest['topic']}'); choose another project_name"
            ),
        }
    (proj_dir / "sources").mkdir(parents=True, exist_ok=True)

    dossier = generate_dossier_markdown(topic, archetype)
    (proj_dir / "notebooklm_dossier.md").write_text(dossier, encoding="utf-8")
    _write_script_seed(proj_dir, topic, archetype)

    manifest_path = proj_dir / "sources" / "manifest.json"
    if not manifest_path.is_file():
        manifest_path.write_text(
            json.dumps(
                {"topic": topic, "archetype": archetype}, indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
    script_path = proj_dir / "script.json"
    if not script_path.is_file():
        script_path.write_text("[]", encoding="utf-8")
    return 200, {
        "success": True,
        "project_name": slug,
        "dossier_markdown": dossier,
        "sources_manifest": _load_manifest(proj_dir),
    }


def handle_list_sources(project_name: str) -> Tuple[int, Dict[str, Any]]:
    """Step 1: list on-disk source files (with SHA-256) plus the manifest."""
    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    return 200, _sources_payload(proj_dir)


def _register_url_source(
    proj_dir: Path, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    url = str(body.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return 400, {"success": False, "error": "url must start with http:// or https://"}
    title = str(body.get("title", "")).strip() or url
    raw_key = str(body.get("source_id", "")).strip() or title
    key = _slugify(raw_key) or "source"
    manifest = _load_manifest(proj_dir)
    base_key, counter = key, 2
    while key in manifest:
        key = f"{base_key}_{counter}"
        counter += 1
    manifest[key] = {"url": url, "title": title, "primary": bool(body.get("primary", False))}
    sources_dir = proj_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 200, _sources_payload(proj_dir)


def _store_file_source(
    proj_dir: Path, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    filename = Path(str(body.get("filename", "")).strip()).name
    if not filename:
        return 400, {"success": False, "error": "filename is required for file sources"}
    if Path(filename).suffix.lower() not in _ALLOWED_SOURCE_EXTS:
        return 400, {
            "success": False,
            "error": f"Unsupported source type. Allowed: {sorted(_ALLOWED_SOURCE_EXTS)}",
        }
    if body.get("content_base64"):
        try:
            data = base64.b64decode(str(body["content_base64"]), validate=True)
        except (binascii.Error, ValueError):
            return 400, {"success": False, "error": "content_base64 is not valid base64"}
    elif body.get("content") is not None:
        data = str(body["content"]).encode("utf-8")
    else:
        return 400, {"success": False, "error": "content_base64 or content is required"}
    if len(data) > _MAX_SOURCE_BYTES:
        return 400, {"success": False, "error": "Source file exceeds 25 MiB limit"}

    sources_dir = proj_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    try:
        target = _contained_target(sources_dir, filename)
    except ValueError:
        return 400, {"success": False, "error": "Source path escapes the sources directory"}
    target.write_bytes(data)
    manifest = _load_manifest(proj_dir)
    manifest[target.name] = {
        "title": filename,
        "filename": filename,
        "sha256": compute_file_sha256(target),
        "primary": bool(body.get("primary", False)),
    }
    (sources_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 200, _sources_payload(proj_dir)


def handle_add_source(
    project_name: str, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """Step 1: register a source URL or store an uploaded source file."""
    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    if str(body.get("url", "")).strip():
        return _register_url_source(proj_dir, body)
    return _store_file_source(proj_dir, body)


def handle_ingest(
    project_name: str, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """Step 2: ingest dialogue markdown into script.json and evidence into claims.json."""
    from veraxi_ymmp.app.history import backup_project_script
    from veraxi_ymmp.editorial.script_ingest import (
        ingest_notebooklm_markdown_to_claims,
        parse_markdown_dialogue,
    )
    from veraxi_ymmp.epistemic.facts import claims_to_json

    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    evidence_md = body.get("evidence_markdown")
    dialogue_md = body.get("dialogue_markdown")
    if not (isinstance(evidence_md, str) and evidence_md.strip()) and not (
        isinstance(dialogue_md, str) and dialogue_md.strip()
    ):
        return 400, {
            "success": False,
            "error": "evidence_markdown or dialogue_markdown is required",
        }

    script: List[Dict[str, Any]] = _load_script(proj_dir)
    dialogue_ingested = False
    if isinstance(dialogue_md, str) and dialogue_md.strip():
        entries = parse_markdown_dialogue(dialogue_md)
        if not entries:
            return 400, {
                "success": False,
                "error": "dialogue_markdown contained no recognizable dialogue lines; script left unchanged",
            }
        script = [dict(e) for e in entries]
        dialogue_ingested = True
        backup_project_script(proj_dir, reason="studio_ingest")
        (proj_dir / "dialogue_raw.md").write_text(dialogue_md, encoding="utf-8")
        (proj_dir / "script.json").write_text(
            json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    claim_count = 0
    claims_path = proj_dir / "claims.json"
    if claims_path.is_file():
        existing = _load_json_file(claims_path, [])
        claim_count = len(existing) if isinstance(existing, list) else 0
    effective_evidence: Optional[str] = None
    if isinstance(evidence_md, str) and evidence_md.strip():
        effective_evidence = evidence_md
        (proj_dir / "evidence.md").write_text(evidence_md, encoding="utf-8")
    elif dialogue_ingested:
        # Evidence may have been ingested before any dialogue existed; its
        # claims were built against an empty script. Rebuild them now that
        # the script is known instead of leaving the stale empty ledger.
        stored_evidence = proj_dir / "evidence.md"
        if stored_evidence.is_file():
            stored_text = stored_evidence.read_text(encoding="utf-8")
            if stored_text.strip():
                effective_evidence = stored_text
    if effective_evidence is not None:
        claims = ingest_notebooklm_markdown_to_claims(
            script,
            effective_evidence,
            manifest=_load_manifest(proj_dir) or None,
            sources_dir=proj_dir / "sources",
        )
        claims_path.write_text(claims_to_json(claims), encoding="utf-8")
        claim_count = len(claims)
    return 200, {
        "success": True,
        "cut_count": len(script),
        "claim_count": claim_count,
        "script": script,
    }


def _serialize_fact_results(outcome: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    claims: List[Dict[str, Any]] = []
    counts = {"supported": 0, "unsupported": 0, "insufficient": 0}
    for result in outcome.results:
        raw_verdict = str(getattr(result.verdict, "value", result.verdict)).lower()
        mapped = _VERDICT_MAP.get(raw_verdict, "INSUFFICIENT")
        if mapped == "SUPPORTED":
            counts["supported"] += 1
        elif mapped == "UNSUPPORTED":
            counts["unsupported"] += 1
        else:
            counts["insufficient"] += 1
        claim = result.claim
        claims.append(
            {
                "id": claim.id,
                "cut_index": claim.cut_index,
                "text": claim.text,
                "verdict": mapped,
                "verdict_raw": raw_verdict,
                "reason": result.reason,
                "quote_errors": list(result.quote_errors),
                "evidence_quotes": [e.quote for e in claim.evidence],
            }
        )
    summary: Dict[str, Any] = {**counts, "total": len(claims), "claims": claims}
    return summary, claims


def handle_validate(project_name: str) -> Tuple[int, Dict[str, Any]]:
    """Step 3: retention pacing audit plus epistemic fact audit gate."""
    from veraxi_ymmp.editorial.pacing import audit_script_pacing

    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    script_path = proj_dir / "script.json"
    if not script_path.is_file():
        return 404, {"success": False, "error": f"script.json not found: {project_name}"}
    script = _load_script(proj_dir)

    report = audit_script_pacing(script)
    pacing_violations = [dataclasses.asdict(v) for v in report.violations]
    cast_balance = {
        name: stats.cut_ratio for name, stats in report.character_stats.items()
    }

    fact_summary: Dict[str, Any] = {
        "supported": 0,
        "unsupported": 0,
        "insufficient": 0,
        "total": 0,
        "claims": [],
    }
    fact_blocked = False
    fact_report: Optional[str] = None
    fact_error: Optional[str] = None
    try:
        draft_project_claims(script_path, script)
        outcome = audit_project_facts(script_path)
        fact_summary, _claims = _serialize_fact_results(outcome)
        fact_blocked = outcome.blocked
        fact_report = outcome.report_path.name
    except FileNotFoundError as exc:
        fact_error = str(exc)

    passed = (
        report.retention_score >= 80
        and fact_summary["unsupported"] == 0
        and not fact_blocked
        and fact_error is None
    )
    return 200, {
        "success": True,
        "passed": passed,
        "retention_score": report.retention_score,
        "pacing_is_healthy": report.is_healthy,
        "pacing_summary": report.summary,
        "cast_balance": cast_balance,
        "character_stats": {
            name: dataclasses.asdict(stats)
            for name, stats in report.character_stats.items()
        },
        "pacing_violations": pacing_violations,
        "fact_summary": fact_summary,
        "fact_blocked": fact_blocked,
        "fact_report": fact_report,
        "fact_error": fact_error,
    }


def handle_qa(project_name: str) -> Tuple[int, Dict[str, Any]]:
    """Step 5: multimodal QA audit; missing prerequisites fail closed, not 500."""
    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    try:
        report = run_project_qa(proj_dir)
    except (FileNotFoundError, ValueError) as exc:
        return 200, {
            "success": False,
            "passed": False,
            "checks": [
                {"name": "prerequisites", "passed": False, "detail": str(exc)}
            ],
            "frames": [],
            "missing_audio": [],
            "coverage_issues": [],
            "thumbnail_issues": [],
        }

    quoted = urllib.parse.quote(project_name)
    frames: List[Dict[str, Any]] = []
    for key, info in report.get("frames", {}).items():
        filename = Path(str(info.get("frame_path", ""))).name
        if not filename:
            continue
        frames.append(
            {
                "key": key,
                "label": _FRAME_LABELS.get(key, key),
                "url": f"/api/projects/{quoted}/media/qa_frames/{filename}",
                "cut_index": info.get("cut_index"),
                "timestamp_sec": info.get("timestamp_sec"),
                "speaker": info.get("speaker"),
                "text": info.get("text"),
            }
        )
    missing_audio = list(report.get("missing_audio", []))
    coverage_issues = list(report.get("coverage_issues", []))
    thumbnail_issues = list(report.get("thumbnail_issues", []))
    checks = [
        {
            "name": "tts_coverage",
            "passed": not missing_audio,
            "detail": (
                "100% TTS audio coverage"
                if not missing_audio
                else f"Missing audio: {', '.join(missing_audio)}"
            ),
        },
        {
            "name": "speaker_coverage",
            "passed": not coverage_issues,
            "detail": "; ".join(coverage_issues) or "All speakers covered",
        },
        {
            "name": "thumbnail",
            "passed": not thumbnail_issues,
            "detail": "; ".join(thumbnail_issues) or "Thumbnail checks passed",
        },
        {
            "name": "keyframes",
            "passed": bool(frames),
            "detail": f"{len(frames)} milestone keyframe(s) extracted",
        },
    ]
    return 200, {
        "success": bool(report.get("success")),
        "passed": bool(report.get("success"))
        and all(check["passed"] for check in checks),
        "checks": checks,
        "frames": frames,
        "missing_audio": missing_audio,
        "coverage_issues": coverage_issues,
        "thumbnail_issues": thumbnail_issues,
        "total_cuts": report.get("total_cuts"),
        "video_duration_sec": report.get("video_duration_sec"),
    }


def handle_notebooklm_prompt(
    project_name: str,
) -> Tuple[int, Dict[str, Any]]:
    """Step 3b: build the post-script NotebookLM audit prompt (CLI parity).

    Mirrors ``veraxi-ymmp verify-notebooklm <project>`` without a reply:
    writes ``notebooklm_audit_prompt.md`` into the project and returns the
    prompt text so the GUI can offer it as a copy-paste bridge.
    """
    from veraxi_ymmp.editorial.notebooklm_verify import (
        build_post_script_audit_prompt,
    )

    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    if not (proj_dir / "script.json").is_file():
        return 400, {
            "success": False,
            "error": "script.json not found; ingest a script first",
        }
    try:
        prompt = build_post_script_audit_prompt(proj_dir)
    except (ValueError, FileNotFoundError) as exc:
        return 400, {"success": False, "error": str(exc)}
    (proj_dir / "notebooklm_audit_prompt.md").write_text(prompt, encoding="utf-8")
    return 200, {"success": True, "prompt": prompt}


def handle_notebooklm_verify(
    project_name: str, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """Step 3b: reconcile a pasted NotebookLM audit table into claims.json.

    Same fail-closed semantics as the CLI: a reply with no valid 7-column
    rows is rejected with nothing written, flagged rows produce the
    re-prompt block, and the epistemic gate is re-run afterwards.
    """
    from veraxi_ymmp.editorial.notebooklm_verify import (
        reconcile_notebooklm_audit,
    )

    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    audit_md = body.get("audit_md")
    if not isinstance(audit_md, str) or not audit_md.strip():
        return 400, {"success": False, "error": "audit_md is required"}
    script_path = proj_dir / "script.json"
    if not script_path.is_file():
        return 400, {
            "success": False,
            "error": "script.json not found; ingest a script first",
        }
    try:
        res = reconcile_notebooklm_audit(proj_dir, audit_md)
    except ValueError as exc:
        return 200, {"success": False, "passed": False, "error": str(exc)}

    outcome = audit_project_facts(script_path)
    gate_blockers = [
        {
            "claim_id": fail.claim.id,
            "verdict": fail.verdict.value,
            "reason": fail.reason,
        }
        for fail in outcome.blockers
    ]
    return 200, {
        "success": True,
        "passed": bool(res.passed and not outcome.blockers),
        "supported_count": res.supported_count,
        "flagged_rows": res.flagged_rows,
        "reprompt_block": res.reprompt_block,
        "gate_blockers": gate_blockers,
        "claims_count": len(res.updated_claims),
    }


# --- Step 1b: external AI clip ingest (ingest-clips parity) --------------
#
# Clips are uploaded into <project>/clip_inbox/ and ingested into
# <project>/clips/ by the same library functions as the CLI
# (clip_ingest.ingest_clips / ingest_clips_from_manifest), so the WP8
# all-or-nothing manifest matching and the atomic publish apply in the
# GUI exactly as on the command line. Ingest re-encodes with ffmpeg and
# can take minutes, so it runs as a polled job, not a synchronous POST.

_MAX_CLIP_BYTES = 100 * 1024 * 1024
_clip_jobs: Dict[str, Dict[str, Any]] = {}
_clip_jobs_lock = threading.Lock()


def _clips_state(proj_dir: Path) -> Dict[str, Any]:
    inbox_dir = proj_dir / "clip_inbox"
    inbox: List[Dict[str, Any]] = []
    if inbox_dir.is_dir():
        for entry in sorted(inbox_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS:
                inbox.append(
                    {"name": entry.name, "size": entry.stat().st_size}
                )
    clips: List[Dict[str, Any]] = []
    manifest_path = proj_dir / "clips" / "manifest.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                clips = list(data.get("clips", []))
        except (OSError, json.JSONDecodeError):
            clips = []
    return {"inbox": inbox, "clips": clips}


def handle_list_clips(project_name: str) -> Tuple[int, Dict[str, Any]]:
    """Step 1b: current clip inbox contents + ingested clips manifest."""
    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    return 200, {"success": True, **_clips_state(proj_dir)}


def handle_upload_clip(
    project_name: str, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """Step 1b: upload one clip file (base64) into the project's clip inbox."""
    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    filename = body.get("filename")
    content_b64 = body.get("content_base64")
    if not isinstance(filename, str) or not filename:
        return 400, {"success": False, "error": "filename is required"}
    if not isinstance(content_b64, str) or not content_b64:
        return 400, {"success": False, "error": "content_base64 is required"}
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in ("", ".", ".."):
        return 400, {"success": False, "error": "filename must be a bare file name"}
    if Path(safe_name).suffix.lower() not in VIDEO_EXTENSIONS:
        return 400, {
            "success": False,
            "error": f"unsupported clip type: {Path(safe_name).suffix} "
            f"(allowed: {', '.join(sorted(VIDEO_EXTENSIONS))})",
        }
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError):
        return 400, {"success": False, "error": "content_base64 is not valid base64"}
    if len(raw) > _MAX_CLIP_BYTES:
        return 400, {
            "success": False,
            "error": f"clip exceeds the {_MAX_CLIP_BYTES // (1024 * 1024)}MB "
            "upload limit; place it in the project clip_inbox folder directly "
            "and ingest from there",
        }
    inbox_dir = (proj_dir / "clip_inbox").resolve()
    if inbox_dir.parent != proj_dir.resolve():
        return 400, {"success": False, "error": "Invalid clip inbox path"}
    inbox_dir.mkdir(parents=True, exist_ok=True)
    target = inbox_dir / safe_name
    if target.resolve().parent != inbox_dir:
        return 400, {"success": False, "error": "Invalid clip file name"}
    target.write_bytes(raw)
    return 200, {"success": True, **_clips_state(proj_dir)}


def handle_ingest_clips_start(
    project_name: str, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """Step 1b: start a clip ingest job (manifest mode when text is given)."""
    try:
        proj_dir = _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    if not proj_dir.is_dir():
        return 404, {"success": False, "error": f"Project not found: {project_name}"}
    inbox_dir = proj_dir / "clip_inbox"
    if not inbox_dir.is_dir() or not any(inbox_dir.iterdir()):
        return 400, {
            "success": False,
            "error": "clip inbox is empty; upload at least one clip first",
        }
    manifest_text = body.get("manifest_text")
    if manifest_text is not None and not isinstance(manifest_text, str):
        return 400, {"success": False, "error": "manifest_text must be a string"}
    use_manifest = bool(manifest_text and manifest_text.strip())

    with _clip_jobs_lock:
        if any(j["status"] == "running" for j in _clip_jobs.values()):
            return 409, {
                "success": False,
                "error": "a clip ingest job is already running",
            }
        job_id = uuid.uuid4().hex[:12]
        _clip_jobs[job_id] = {"status": "running", "result": None, "error": None}

    def _run() -> None:
        result: Optional[Dict[str, Any]] = None
        error: Optional[str] = None
        try:
            out_dir = proj_dir / "clips"
            if use_manifest:
                manifest_path = proj_dir / "clip-manifest.json"
                manifest_path.write_text(manifest_text or "", encoding="utf-8")
                result = ingest_clips_from_manifest(
                    inbox_dir, manifest_path, output_dir=out_dir
                )
            else:
                result = ingest_clips(inbox_dir, output_dir=out_dir)
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:  # ffmpeg missing etc.: surface, don't 500
            error = f"clip ingest failed: {exc}"
        with _clip_jobs_lock:
            _clip_jobs[job_id] = {
                "status": "done",
                "result": result,
                "error": error,
            }

    threading.Thread(target=_run, daemon=True).start()
    return 200, {"success": True, "job_id": job_id, "mode": "manifest" if use_manifest else "inbox"}


def handle_ingest_clips_status(
    project_name: str, body: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """Step 1b: poll a clip ingest job started for this project."""
    try:
        _project_dir(project_name)
    except ValueError:
        return 400, {"success": False, "error": "Invalid project name"}
    job_id = body.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        return 400, {"success": False, "error": "job_id is required"}
    with _clip_jobs_lock:
        job = _clip_jobs.get(job_id)
        if job is None:
            return 404, {"success": False, "error": f"unknown job_id: {job_id}"}
        payload: Dict[str, Any] = {"success": True, "status": job["status"]}
        if job["status"] == "done":
            if job["error"]:
                payload["error"] = job["error"]
            else:
                result = job["result"] or {}
                payload["result"] = {
                    "clips": result.get("clips", []),
                    "rejected": result.get("rejected", []),
                    "matching_aborted": bool(result.get("matching_aborted", False)),
                    "ingest_aborted": bool(result.get("ingest_aborted", False)),
                    "from_manifest": result.get("from_manifest"),
                }
                payload["ok"] = bool(result.get("clips")) and not (
                    result.get("matching_aborted") or result.get("ingest_aborted")
                )
        return 200, payload
