"""Script providers: topic + evidence dossier -> validated director script.

This module implements the ``ScriptProvider`` port (``core/ports.py``) for
the Gemini-web workflow. The CLI never calls an LLM API; instead a provider
produces the script. The only implementation today is
``ManualHandoffProvider``: it renders the export-spec prompt with the topic
and the evidence dossier, the user pastes that prompt into a web chat
(e.g. Gemini), pastes the JSON reply back into the terminal, and the
provider validates it — printing the standard LLM re-prompt block on
failure and looping until the reply converges. It is the same loop the
Studio GUI runs, but headless and scriptable from the CLI.

An ``api`` provider can be added behind ``generate_with_provider`` once an
API key exists; until then it fails loudly instead of silently falling
back to the manual flow.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from veraxi_ymmp.core.constants import DEFAULT_SPEAKER_MAP
from veraxi_ymmp.core.schema import get_director_script_schema
from veraxi_ymmp.core.script import DirectorScriptEntry, validate_director_script

PASTE_TERMINATOR = "---END---"

OutputFn = Callable[[str], None]
PasteFn = Callable[[], str]
PayloadValidator = Callable[[Dict[str, Any]], List[str]]

_EXTRA_VALIDATOR_CTX: contextvars.ContextVar[Optional[PayloadValidator]] = (
    contextvars.ContextVar("veraxi_extra_validator", default=None)
)
_LAST_PROVIDER: Optional["ManualHandoffProvider"] = None


@contextlib.contextmanager
def _using_extra_validator(
    validator: Optional[PayloadValidator],
) -> Iterator[None]:
    """Temporarily bind an extra payload validator for generate_with_provider."""
    token = _EXTRA_VALIDATOR_CTX.set(validator)
    try:
        yield
    finally:
        _EXTRA_VALIDATOR_CTX.reset(token)


class _MultiValidationError(ValueError):
    """Carry multiple structured error lines through ValueError handoff."""

    def __init__(self, errors: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def format_reprompt_block(errors: List[str]) -> str:
    """Format validation errors as the standard copy-paste re-prompt block.

    Uses the same wording as ``veraxi-ymmp validate`` so the manual loop
    feels identical whether it is driven from the CLI or the Studio GUI.
    """
    lines = [
        "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================",
        "The script you provided failed schema validation with the following errors:",
    ]
    lines.extend(f"  - [SCHEMA] {error}" for error in errors)
    lines.append(
        "Please fix these specific entries while preserving the rest of the script, "
        "and return the complete corrected JSON block."
    )
    lines.append("==========================================================================")
    return "\n".join(lines)


def build_script_prompt(topic: str, dossier: str) -> str:
    """Build the script-generation prompt, reusing the export-spec template.

    The base text is the same Universal AI Prompt that
    ``veraxi-ymmp export-spec`` emits (including its Available Characters
    appendix); the topic, the evidence dossier, and the JSON output
    contract are appended.
    """
    template_path = (
        Path(__file__).resolve().parent.parent / "templates" / "UNIVERSAL_AI_PROMPT.md"
    )
    prompt = template_path.read_text(encoding="utf-8")
    chars = ", ".join(f"`{c}`" for c in DEFAULT_SPEAKER_MAP.keys())
    prompt += f"\n\n## Available Characters\n{chars}\n"
    schema = json.dumps(get_director_script_schema(), indent=2, ensure_ascii=False)
    prompt += (
        f"\n\n## Topic\n{topic}\n"
        f"\n## Evidence Dossier\n{dossier}\n"
        "\n## Output Contract\n"
        "Return ONLY a JSON object of the form "
        '{"script": [...], "broll_manifest": [...]} — no prose, no '
        "commentary. The \"script\" value is an array of director "
        "script entries conforming to this JSON Schema:\n"
        f"```json\n{schema}\n```\n"
        "The \"broll_manifest\" value is an array of slide definition "
        "objects, one per slide referenced by an entry's \"image\" "
        "field, or an empty array when no slides are referenced. "
        "Do NOT invent video clip_ids; standard B-roll slides are "
        "rendered automatically from \"broll_manifest\". Optionally, "
        "include a \"thumbnail_config\" object for the 3-split thumbnail.\n"
    )
    return prompt


def extract_script_json(text: str) -> Any:
    """Extract the JSON value from a pasted web-chat reply.

    Accepts a bare JSON document, a fenced ```json block, or prose with
    a JSON object or array embedded in it. The object span is tried
    before the array span so a prose-wrapped object reply keeps its
    ``broll_manifest`` instead of silently reducing to the inner
    ``script`` array. Raises ValueError when nothing parseable is
    present so the caller can re-prompt.
    """
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    candidates = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            candidates.append((start, -(end - start), cleaned[start : end + 1]))
    # Earliest span first, outermost first on ties: a prose-wrapped
    # array must yield the array, not its first entry's object span.
    for _start, _neg_len, span in sorted(candidates):
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            continue
    raise ValueError(
        "Pasted reply does not contain a JSON object or array: "
        f"{cleaned[:120]!r}"
    )


def _canonical_broll_entry(entry: Any) -> Any:
    """Canonicalize one extracted slide entry to the object shape.

    Legacy appended-style entries (from the pre-WP5 low-tier
    prompt) mark themselves with ``"type": "broll_manifest"`` and
    carry the layout in ``slide_type``; the canonical object shape
    (and the slide renderer) uses ``type`` for the layout itself.
    """
    if not isinstance(entry, dict):
        return entry
    entry = dict(entry)
    slide_type = entry.pop("slide_type", None)
    if entry.get("type") == "broll_manifest":
        entry.pop("type")
    if slide_type is not None:
        entry = {"type": slide_type, **entry}
    return entry


def normalize_script_payload(data: Any) -> dict:
    """Normalize a parsed reply to the single object contract (WP5).

    The canonical shape is ``{"script": [...], "broll_manifest":
    [...]}``. Two legacy shapes are accepted leniently so old
    prompts and saved replies keep working:

    * a bare array of script entries (``broll_manifest`` is empty);
    * an array whose slide definitions are appended as
      ``{"type": "broll_manifest", ...}`` entries (extracted into
      ``broll_manifest`` and canonicalized).
    """
    if isinstance(data, dict):
        script = data.get("script")
        if not isinstance(script, list):
            raise ValueError(
                "Script reply object must contain a \"script\" array."
            )
        raw_broll = data.get("broll_manifest", [])
        if raw_broll is None:
            raw_broll = []
        if not isinstance(raw_broll, list):
            raise ValueError(
                "Script reply \"broll_manifest\" must be an array."
            )
        broll = raw_broll
        return {"script": script, "broll_manifest": list(broll)}
    if isinstance(data, list):
        script_entries: List[Any] = []
        broll_entries: List[Any] = []
        for entry in data:
            if isinstance(entry, dict) and entry.get("type") == (
                "broll_manifest"
            ):
                broll_entries.append(_canonical_broll_entry(entry))
            else:
                script_entries.append(entry)
        return {"script": script_entries, "broll_manifest": broll_entries}
    raise ValueError(
        "Script reply must be a JSON object or array, got "
        f"{type(data).__name__}."
    )


def validate_pasted_payload(raw: str) -> dict:
    """Parse a pasted reply into the normalized, validated payload.

    Returns ``{"script": [validated entries], "broll_manifest":
    [...]}`` — the single contract every prompt source now emits.
    """
    payload = normalize_script_payload(extract_script_json(raw))
    entries = validate_director_script(payload["script"])
    return {"script": entries, "broll_manifest": payload["broll_manifest"]}


def validate_pasted_script(raw: str) -> List[DirectorScriptEntry]:
    """Parse a pasted reply and return the validated director script."""
    payload = normalize_script_payload(extract_script_json(raw))
    return validate_director_script(payload["script"])


def _read_paste_from_stdin() -> str:
    """Read a pasted reply from stdin until EOF or the terminator line."""
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == PASTE_TERMINATOR:
            break
        lines.append(line)
    return "\n".join(lines)


def _extract_thumbnail_config(raw: str) -> Optional[Dict[str, Any]]:
    """Extract optional ``thumbnail_config`` dict from a pasted JSON reply."""
    try:
        data = extract_script_json(raw)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("thumbnail_config"), dict):
        return dict(data["thumbnail_config"])
    return None


def _collect_slide_texts(spec: Dict[str, Any]) -> List[str]:
    """Collect visible text elements from a broll_manifest entry for load checks."""
    skip_keys = {
        "type", "filename", "theme_color", "color", "is_vertical",
        "image_path", "image", "asset", "layout", "show_caption",
        "show_header", "show_citation",
    }
    color_tokens = {"blue", "emerald", "amber", "purple", "rose", "red", "green"}
    texts: List[str] = []
    for k, v in spec.items():
        if k in skip_keys or v is None:
            continue
        if isinstance(v, str) and v.strip():
            texts.append(v.strip())
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip().lower() not in color_tokens:
                    texts.append(item.strip())
                elif isinstance(item, (list, tuple)):
                    for sub in item:
                        if isinstance(sub, str) and sub.strip().lower() not in color_tokens:
                            texts.append(sub.strip())
                elif isinstance(item, dict):
                    for sub_v in item.values():
                        if isinstance(sub_v, str) and sub_v.strip().lower() not in color_tokens:
                            texts.append(sub_v.strip())
    return texts


def _validate_cuts_and_broll(
    payload: Dict[str, Any], project_dir: Path
) -> List[str]:
    """Validate visible cut lengths, unmapped ASCII tokens, and slide load."""
    from veraxi_ymmp.audio.phonetics import find_unmapped_ascii_tokens, strip_phonetic_ruby
    from veraxi_ymmp.graphics.broll import MAX_SLIDE_CHARS, MAX_SLIDE_ELEMENTS, check_cognitive_load

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

    for s_idx, spec in enumerate(payload.get("broll_manifest", [])):
        if not isinstance(spec, dict):
            errors.append(f"broll_manifest[{s_idx}] must be an object.")
            continue
        title = str(spec.get("title") or spec.get("filename") or f"slide_{s_idx}")
        try:
            check_cognitive_load(
                title,
                _collect_slide_texts(spec),
                max_chars=MAX_SLIDE_CHARS,
                max_elements=MAX_SLIDE_ELEMENTS + 6,
            )
        except ValueError as exc:
            errors.append(f"[BROLL] {exc}")
    return errors


def _run_fact_gate_check(
    resolved_dir: Path,
    payload: Dict[str, Any],
    script_entries: Sequence[Any],
    evidence_markdown: Optional[str],
    manifest_data: Optional[Dict[str, Any]],
) -> List[str]:
    """Build claims from NotebookLM evidence when present and run audit_project_facts."""
    from veraxi_ymmp.editorial.script_ingest import (
        ingest_notebooklm_markdown_to_claims,
        parse_markdown_evidence_table,
    )
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
    from veraxi_ymmp.epistemic.facts import claims_to_json

    ev_text = evidence_markdown
    if ev_text is None and (resolved_dir / "evidence.md").is_file():
        ev_text = (resolved_dir / "evidence.md").read_text(encoding="utf-8")

    claims_path = resolved_dir / "claims.json"
    sources_dir = resolved_dir / "sources"
    manifest_path = sources_dir / "manifest.json"
    sources_dir_existed = sources_dir.is_dir()
    pre_source_files = set(sources_dir.iterdir()) if sources_dir_existed else set()

    tmp_script = resolved_dir / ".candidate_script.tmp.json"
    backups: List[Tuple[Path, Optional[str]]] = []
    try:
        if ev_text is not None and parse_markdown_evidence_table(ev_text):
            mf = manifest_data
            if mf is None and manifest_path.is_file():
                try:
                    mf = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    mf = None
            backups.append(
                (claims_path, claims_path.read_text(encoding="utf-8") if claims_path.is_file() else None)
            )
            backups.append(
                (manifest_path, manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None)
            )
            for item in pre_source_files:
                if item.is_file() and item.suffix.lower() == ".md":
                    backups.append((item, item.read_text(encoding="utf-8")))
            claims = ingest_notebooklm_markdown_to_claims(
                script_entries, ev_text, manifest=mf, sources_dir=sources_dir
            )
            claims_path.write_text(claims_to_json(claims), encoding="utf-8")

        if not claims_path.is_file():
            return []

        tmp_script.write_text(
            json.dumps(list(script_entries), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        for fname, key in (("broll_manifest.json", "broll_manifest"), ("thumbnail_config.json", "thumbnail_config")):
            val = payload.get(key)
            if val:
                fpath = resolved_dir / fname
                backups.append((fpath, fpath.read_text(encoding="utf-8") if fpath.is_file() else None))
                fpath.write_text(json.dumps(val, indent=2, ensure_ascii=False), encoding="utf-8")
        outcome = audit_project_facts(tmp_script)
        return [
            f"[FACTS] {r.claim.id} (cut {r.claim.cut_index}) {r.verdict.value}: {r.reason}"
            for r in outcome.blockers
        ]
    finally:
        tmp_script.unlink(missing_ok=True)
        for fpath, prev in reversed(backups):
            if prev is None:
                fpath.unlink(missing_ok=True)
            else:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(prev, encoding="utf-8")
        if sources_dir.is_dir():
            for item in list(sources_dir.iterdir()):
                if item not in pre_source_files and item.is_file():
                    item.unlink(missing_ok=True)
            if not sources_dir_existed and not any(sources_dir.iterdir()):
                sources_dir.rmdir()


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

        if audit_pacing:
            from veraxi_ymmp.editorial.pacing import audit_script_pacing
            report = audit_script_pacing(list(script_entries))
            if report.retention_score < 80:
                pacing_msgs = [
                    f"[PACING {v.rule_name}] {v.message} (Remedy: {v.remedy})"
                    for v in report.violations
                    if v.severity in {"ERROR", "WARNING"}
                ]
                errors.extend(
                    pacing_msgs
                    or [f"[PACING] Retention score {report.retention_score}/100 is below 80."]
                )

        if audit_facts:
            errors.extend(
                _run_fact_gate_check(
                    resolved_dir, payload, script_entries, evidence_markdown, manifest_data
                )
            )
        return errors

    return _validate


class ManualHandoffProvider:
    """ScriptProvider that hands off to a human + web chat (e.g. Gemini).

    Workflow: print the prompt (and save it to ``prompt_path`` when given),
    read one pasted reply, validate it, and on failure print the
    re-prompt block and read another reply, until a valid script arrives.
    EOF or an empty paste aborts with ValueError — the loop never spins
    without input. ``paste_fn``/``output_fn`` are injectable so the loop
    is unit-testable and scriptable.
    """

    def __init__(
        self,
        paste_fn: Optional[PasteFn] = None,
        output_fn: OutputFn = print,
        prompt_path: Optional[Path] = None,
        max_attempts: Optional[int] = None,
        extra_validator: Optional[PayloadValidator] = None,
    ) -> None:
        self._paste_fn = paste_fn or _read_paste_from_stdin
        self._output_fn = output_fn
        self._prompt_path = prompt_path
        self._max_attempts = max_attempts
        self._extra_validator = extra_validator
        # The normalized payload of the last successful paste. The
        # ScriptProvider port returns only the script entries, so the
        # reply's broll_manifest is surfaced here instead of being
        # silently dropped at ingest.
        self.last_broll_manifest: List[Any] = []
        self.last_thumbnail_config: Optional[Dict[str, Any]] = None
        self.last_payload: Optional[dict] = None

    def generate_script(self, topic: str, dossier: str) -> List[DirectorScriptEntry]:
        prompt = build_script_prompt(topic, dossier)
        if self._prompt_path is not None:
            self._prompt_path.write_text(prompt, encoding="utf-8")
            self._output_fn(f"Prompt written to {self._prompt_path}")
        self._output_fn(prompt)
        self._output_fn(
            "Paste the web chat's JSON reply below, then end the paste with "
            f"a line containing only {PASTE_TERMINATOR} (or EOF / Ctrl-D)."
        )
        attempts = 0
        while True:
            attempts += 1
            try:
                raw = self._paste_fn()
            except EOFError as exc:
                raise ValueError(
                    "Manual handoff aborted: input ended before a script was pasted."
                ) from exc
            if not raw.strip():
                raise ValueError("Manual handoff aborted: pasted reply was empty.")
            try:
                payload = validate_pasted_payload(raw)
                thumb_cfg = _extract_thumbnail_config(raw)
                if self._extra_validator is not None:
                    val_payload = (
                        {**payload, "thumbnail_config": thumb_cfg}
                        if thumb_cfg is not None
                        else payload
                    )
                    extra_errors = self._extra_validator(val_payload)
                    if extra_errors:
                        raise _MultiValidationError(extra_errors)
                self.last_payload = payload
                self.last_broll_manifest = payload["broll_manifest"]
                self.last_thumbnail_config = thumb_cfg
                entries: List[DirectorScriptEntry] = payload["script"]
                return entries
            except ValueError as exc:
                err_list = exc.errors if isinstance(exc, _MultiValidationError) else [str(exc)]
                self._output_fn(format_reprompt_block(err_list))
                if self._max_attempts is not None and attempts >= self._max_attempts:
                    raise ValueError(
                        f"Manual handoff did not converge after {attempts} "
                        f"attempt(s): {exc}"
                    ) from exc


def generate_with_provider(
    name: Optional[str],
    topic: str,
    dossier: str,
    prompt_path: Optional[Path] = None,
    paste_fn: Optional[PasteFn] = None,
    output_fn: OutputFn = print,
) -> List[DirectorScriptEntry]:
    """Dispatch to the named ScriptProvider (``manual`` is the default).

    ``api`` is reserved for a future key-backed provider and raises
    RuntimeError until one is configured; unknown names raise ValueError.
    """
    global _LAST_PROVIDER
    _LAST_PROVIDER = None
    provider_name = (name or "manual").lower()
    if provider_name == "manual":
        provider = ManualHandoffProvider(
            paste_fn=paste_fn,
            output_fn=output_fn,
            prompt_path=prompt_path,
            extra_validator=_EXTRA_VALIDATOR_CTX.get(),
        )
        _LAST_PROVIDER = provider
        return provider.generate_script(topic, dossier)
    if provider_name == "api":
        raise RuntimeError(
            "Script provider 'api' is not available: no LLM API key is "
            "configured. Use --provider manual with a web chat instead."
        )
    raise ValueError(f"Unknown script provider: {name!r} (expected 'manual' or 'api')")


def generate_script_file(
    provider_name: Optional[str],
    topic: str,
    dossier: str,
    script_path: Path,
    prompt_path: Optional[Path] = None,
    extra_validator: Optional[PayloadValidator] = None,
) -> List[DirectorScriptEntry]:
    """Generate a script via the named provider and write it to script_path.

    Shared by the ``ideate`` and ``ingest-script`` CLI commands. Also writes
    ``broll_manifest.json`` and ``thumbnail_config.json`` beside ``script_path``
    when the provider reply includes them. An unavailable provider (e.g. ``api``
    without a key) is a clean CLI error (exit 2), not a traceback.
    """
    global _LAST_PROVIDER
    _LAST_PROVIDER = None
    try:
        with _using_extra_validator(extra_validator):
            entries = generate_with_provider(
                provider_name, topic, dossier, prompt_path=prompt_path
            )
    except RuntimeError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        raise SystemExit(2) from exc
    script_path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if _LAST_PROVIDER is not None:
        if _LAST_PROVIDER.last_broll_manifest:
            broll_path = script_path.parent / "broll_manifest.json"
            broll_path.write_text(
                json.dumps(_LAST_PROVIDER.last_broll_manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if _LAST_PROVIDER.last_thumbnail_config:
            thumb_path = script_path.parent / "thumbnail_config.json"
            thumb_path.write_text(
                json.dumps(_LAST_PROVIDER.last_thumbnail_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    return entries
