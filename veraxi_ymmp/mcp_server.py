"""MCP tools for conversational control of the veraxi-ymmp pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .compiler import YMMPCompiler
from .config import CompilerConfig
from .script import (
    validate_director_against_writer,
    validate_director_script,
    validate_writer_script,
)
from .template import extract_character_templates, get_timeline, load_template
from .voicevox import NullTTSBackend, VoicevoxClient

mcp = FastMCP("veraxi-ymmp")


def workspace_path(path: str) -> Path:
    """Resolve a path inside the MCP server's workspace."""
    root = Path.cwd().resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path must stay inside the workspace: {path}") from exc
    return candidate


def parse_json(value: str, label: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label} JSON: {exc}") from exc


@mcp.tool()
def inspect_template(template: str) -> Dict[str, Any]:
    """Inspect template timeline shape, characters, and reusable item types."""
    template_data = load_template(str(workspace_path(template)))
    timeline = get_timeline(template_data)
    character_templates = extract_character_templates(template_data)
    items = timeline.get("Items", [])
    return {
        "timeline_layout": "Timeline" if "Timeline" in template_data else "Timelines",
        "fps": timeline.get("VideoInfo", {}).get("FPS"),
        "characters": sorted(character_templates),
        "item_types": [item.get("$type", "") for item in items],
        "item_count": len(items),
        "has_voice_template": any(value["voice"] is not None for value in character_templates.values()),
        "has_tachie_template": any(value["tachie"] is not None for value in character_templates.values()),
    }


@mcp.tool()
def validate_script(
    script_json: str,
    writer_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate Writer or Director JSON and optionally compare it to Writer JSON."""
    data = parse_json(script_json, "script")
    has_director_fields = any(
        isinstance(entry, dict)
        and any(
            key in entry
            for key in (
                "emotion",
                "motion",
                "bgm",
                "sfx",
                "character_position",
                "subtitle_position",
                "subtitle_style",
            )
        )
        for entry in data
    ) if isinstance(data, list) else False

    if has_director_fields:
        validated = validate_director_script(data)
        script_type = "director"
        if writer_json is not None:
            writer = validate_writer_script(parse_json(writer_json, "writer script"))
            validate_director_against_writer(validated, writer)
    else:
        validated = validate_writer_script(data)
        script_type = "writer"

    return {"valid": True, "type": script_type, "entries": validated}


@mcp.tool()
def compile_project(
    template: str,
    script_json: str,
    output: str,
    tts: bool = False,
    voicevox_url: str = "http://localhost:50021",
    default_speaker: int = 3,
    writer_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate and compile a script into a YMM4 project."""
    validation = validate_script(script_json, writer_json)
    script = validation["entries"]
    output_path = workspace_path(output)
    config = CompilerConfig(use_tts=tts, default_speaker_id=default_speaker, voicevox_url=voicevox_url)
    backend = VoicevoxClient(voicevox_url) if tts else NullTTSBackend()
    if tts and not backend.is_available():
        raise RuntimeError(f"VOICEVOX is not available at {voicevox_url}")

    compiler = YMMPCompiler(template_path=workspace_path(template), config=config, tts_backend=backend)
    result = compiler.compile(script, output_path)
    return {
        "output": str(result.output_path),
        "total_frames": result.total_frames,
        "duration_seconds": result.total_duration_seconds,
        "voice_items": result.voice_item_count,
        "tachie_items": result.tachie_item_count,
        "audio_files": [str(path) for path in result.audio_files],
        "warnings": result.warnings,
    }


if __name__ == "__main__":
    mcp.run()
