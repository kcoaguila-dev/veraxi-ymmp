"""MCP tools for conversational control of the veraxi-ymmp pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import os
import subprocess
import tempfile
from PIL import Image

from .broll import render_from_manifest
from .audio_normalizer import normalize_video_audio, PLATFORM_TARGETS
from .logging import logger

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore[no-redef]

from .compiler import YMMPCompiler
from .config import CompilerConfig
from .pipeline import ProjectPipeline
from .script import (
    validate_director_against_writer,
    validate_director_script,
    validate_writer_script,
)
from .template import extract_character_templates, get_timeline, load_template
from .thumbnail import generate_project_thumbnail
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

    validated: List[Any]
    if has_director_fields:
        director_entries = validate_director_script(data)
        script_type = "director"
        if writer_json is not None:
            writer = validate_writer_script(parse_json(writer_json, "writer script"))
            validate_director_against_writer(director_entries, writer)
        validated = director_entries
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


@mcp.tool()
def run_pipeline(project_dir: str, use_tts: bool = True) -> str:
    """Execute the end-to-end ProjectPipeline for a workspace project directory."""
    proj_path = workspace_path(project_dir)

    def cb(stage: str, ratio: float, msg: str) -> None:
        logger.info(f"Progress [{stage}]: {ratio*100}% - {msg}")

    pipeline = ProjectPipeline(use_tts=use_tts, progress_callback=cb)
    res = pipeline.run(proj_path)
    return json.dumps(
        {
            "success": res.success,
            "project_dir": str(res.project_dir),
            "ymmp_path": str(res.ymmp_path) if res.ymmp_path else None,
            "premiere_xml": str(res.premiere_xml) if res.premiere_xml else None,
            "qa_video_path": str(res.qa_video_path) if res.qa_video_path else None,
            "thumbnail_path": str(res.thumbnail_path) if res.thumbnail_path else None,
            "errors": res.errors,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def generate_thumbnail_tool(project_dir: str) -> str:
    """Generate a publication-ready YouTube thumbnail for a workspace project directory."""
    proj_path = workspace_path(project_dir)
    out_path = generate_project_thumbnail(proj_path, out_path=proj_path / "thumbnail.png")
    return str(out_path)



@mcp.tool()
def get_voicevox_health(voicevox_url: str = "http://localhost:50021") -> Dict[str, Any]:
    """Pings the VOICEVOX engine and returns health status and speakers."""
    client = VoicevoxClient(base_url=voicevox_url)
    available = False
    speakers = []
    try:
        available = client.is_available()
        if available:
            speakers = client.get_speakers()
    except Exception as e:
        logger.error(f"Failed to check voicevox health: {e}")

    return {
        "available": available,
        "url": voicevox_url,
        "speakers": speakers
    }

@mcp.tool()
def audition_voice(text: str, speaker_id: int, speed: float = 1.0, voicevox_url: str = "http://localhost:50021") -> Dict[str, Any]:
    """Synthesizes a single test line of dialogue to a temporary cached WAV file."""
    client = VoicevoxClient(base_url=voicevox_url)
    import requests
    import io
    import wave
    try:
        # To alter speed, we must fetch audio query, modify speedScale, then synthesize
        audio_query = client.get_audio_query(text, speaker_id)
        if speed != 1.0:
            audio_query["speedScale"] = speed

        synth_res = requests.post(
            f"{client.base_url}/synthesis",
            params={"speaker": speaker_id},
            json=audio_query,
            headers={"Content-Type": "application/json"},
            timeout=client.timeout,
        )
        synth_res.raise_for_status()
        wav_bytes = synth_res.content

        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration = frames / float(rate)

        phoneme_count = 0
        if "accent_phrases" in audio_query:
            for phrase in audio_query["accent_phrases"]:
                if "moras" in phrase:
                    phoneme_count += len(phrase["moras"])

        if phoneme_count == 0:
            phoneme_count = len(text)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            abs_path = os.path.abspath(f.name)

        return {
            "path": abs_path,
            "duration_seconds": duration,
            "phoneme_count": phoneme_count
        }
    except Exception as e:
        raise RuntimeError(f"Audition failed: {e}")

@mcp.tool()
def render_broll_slides(manifest_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Wraps veraxi_ymmp.broll.render_from_manifest to generate slides."""
    try:
        resolved_manifest = workspace_path(manifest_path)
        if output_dir:
            resolved_out = workspace_path(output_dir)
        else:
            resolved_out = resolved_manifest.parent

        generated_paths = render_from_manifest(resolved_manifest, resolved_out)

        slides = []
        for path in generated_paths:
            try:
                with Image.open(path) as img:
                    width, height = img.size
                slides.append({
                    "path": str(path),
                    "width": width,
                    "height": height
                })
            except Exception as e:
                logger.warning(f"Could not read image dimensions for {path}: {e}")
                slides.append({
                    "path": str(path),
                    "width": 0,
                    "height": 0
                })

        return {"slides": slides}
    except Exception as e:
        raise RuntimeError(f"Failed to render b-roll slides: {e}")

@mcp.tool()
def normalize_project_audio(project_dir: str, platform: str = "youtube") -> Dict[str, Any]:
    """Normalizes video audio for the specified platform."""
    proj_path = workspace_path(project_dir)
    target_video = None

    for candidate in ["final_video.mp4", "qa_test.mp4"]:
        candidate_path = proj_path / candidate
        if candidate_path.exists():
            target_video = candidate_path
            break

    if not target_video:
        raise FileNotFoundError(f"No video artifact found in {proj_path} for normalization.")

    if platform not in PLATFORM_TARGETS:
        raise ValueError(f"Unknown platform: {platform}")

    target = PLATFORM_TARGETS[platform]

    # Try to measure input loudness first
    measured_i = 0.0
    measured_tp = 0.0
    try:
        cmd = [
            "ffmpeg", "-i", str(target_video),
            "-af", "loudnorm=I=-14:print_format=json",
            "-f", "null", "-"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        # Parse the JSON from stderr
        output_str = res.stderr
        import json as _json

        # The JSON output is usually at the end, enclosed in {}
        start_idx = output_str.rfind("{")
        end_idx = output_str.rfind("}")
        if start_idx != -1 and end_idx != -1:
            json_str = output_str[start_idx:end_idx+1]
            data = _json.loads(json_str)
            measured_i = float(data.get("input_i", 0.0))
            measured_tp = float(data.get("input_tp", 0.0))
    except Exception as e:
        logger.warning(f"Failed to measure input loudness: {e}")

    out_file = proj_path / f"{target_video.stem}_{platform}{target_video.suffix}"
    normalized_path = normalize_video_audio(
        input_video=target_video,
        output_video=out_file,
        target_i=target["I"],
        target_tp=target["TP"],
        target_lra=target["LRA"]
    )

    return {
        "output_path": str(normalized_path),
        "target_lufs": target["I"],
        "measured_i": measured_i,
        "measured_tp": measured_tp
    }

@mcp.tool()
def launch_ymm4_desktop(project_dir: str) -> Dict[str, Any]:
    """Locates YMM4 and launches the project .ymmp file."""
    proj_path = workspace_path(project_dir)

    ymm4_path = os.environ.get("YMM4_PATH")
    if not ymm4_path:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            base_dir = Path(local_app_data)
            for subdir in ["YukkuriMovieMaker4", "Programs/YukkuriMovieMaker4"]:
                candidate = base_dir / subdir / "YukkuriMovieMaker.exe"
                if candidate.exists():
                    ymm4_path = str(candidate)
                    break

    if not ymm4_path or not os.path.exists(ymm4_path):
        raise FileNotFoundError("Could not find YukkuriMovieMaker.exe")

    ymmp_dir = proj_path / "ymmp"
    ymmp_file = None
    if ymmp_dir.exists():
        for p in ymmp_dir.glob("*.ymmp"):
            ymmp_file = p
            break

    if not ymmp_file:
        for p in proj_path.glob("*.ymmp"):
            ymmp_file = p
            break

    if not ymmp_file:
        raise FileNotFoundError(f"Could not find a .ymmp file in {proj_path}")

    cmd = [ymm4_path, str(ymmp_file)]
    kwargs: Dict[str, Any] = {}
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)

    try:
        subprocess.Popen(cmd, **kwargs)
        return {
            "launched": True,
            "executable": ymm4_path,
            "project": str(ymmp_file)
        }
    except Exception as e:
        raise RuntimeError(f"Failed to launch YMM4: {e}")


if __name__ == "__main__":
    mcp.run()
