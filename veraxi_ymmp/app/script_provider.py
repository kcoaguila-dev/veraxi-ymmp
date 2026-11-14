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
from typing import Any, Callable, Dict, Iterator, List, Optional

from veraxi_ymmp.app.project_gate import (
    PayloadValidator as PayloadValidator,
    _asset_exists as _asset_exists,
    _backup_project_state as _backup_project_state,
    _collect_slide_texts as _collect_slide_texts,
    _load_json_dict as _load_json_dict,
    _lookup_staged_text as _lookup_staged_text,
    _pacing_errors as _pacing_errors,
    _parse_staged_json as _parse_staged_json,
    _run_fact_gate_check as _run_fact_gate_check,
    _validate_cross_file_and_evidence_scale_parity as _validate_cross_file_and_evidence_scale_parity,
    _validate_cuts_and_broll as _validate_cuts_and_broll,
    build_project_gate_validator as build_project_gate_validator,
    validate_and_reconcile_staged_project as validate_and_reconcile_staged_project,
)
from veraxi_ymmp.core.constants import DEFAULT_SPEAKER_MAP
from veraxi_ymmp.core.schema import get_director_script_schema
from veraxi_ymmp.core.script import DirectorScriptEntry, validate_director_script

PASTE_TERMINATOR = "---END---"

OutputFn = Callable[[str], None]
PasteFn = Callable[[], str]

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
