"""MCP tools for conversational control of the veraxi-ymmp pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import os
import shutil
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
    import requests  # type: ignore
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

def find_ymm4_executable() -> Optional[str]:
    """Auto-detects YukkuriMovieMaker.exe across common install locations, portable folders, and user paths."""
    ymm4_path = os.environ.get("YMM4_PATH")
    if ymm4_path and os.path.exists(ymm4_path):
        return ymm4_path

    which_path = shutil.which("YukkuriMovieMaker.exe") or shutil.which("YukkuriMovieMaker")
    if which_path and os.path.exists(which_path):
        return which_path

    home = Path.home()
    for folder in ["Documents", "Desktop", "Downloads"]:
        d = home / folder
        if d.exists():
            for p in list(d.glob("*YukkuriMovieMaker*/YukkuriMovieMaker.exe")) + list(d.glob("*YMM4*/YukkuriMovieMaker.exe")):
                if p.exists():
                    return str(p)

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        base_dir = Path(local_app_data)
        for subdir in ["YukkuriMovieMaker4", "Programs/YukkuriMovieMaker4"]:
            cand = base_dir / subdir / "YukkuriMovieMaker.exe"
            if cand.exists():
                return str(cand)

    for env_var in ["ProgramFiles", "ProgramFiles(x86)"]:
        pf = os.environ.get(env_var)
        if pf:
            for sub in ["YukkuriMovieMaker4", "YukkuriMovieMaker_v4_Lite"]:
                cand = Path(pf) / sub / "YukkuriMovieMaker.exe"
                if cand.exists():
                    return str(cand)

    for cand in [Path("C:/YukkuriMovieMaker4/YukkuriMovieMaker.exe"), Path("C:/YukkuriMovieMaker_v4_Lite/YukkuriMovieMaker.exe")]:
        if cand.exists():
            return str(cand)

    return None


def spawn_interactive_desktop_process(cmd: str, cwd: Optional[str] = None) -> bool:
    r"""Spawns a GUI process attached to the user's interactive desktop (WinSta0\Default).

    Returns True if successfully launched via Win32 CreateProcessW, False otherwise.
    """
    if os.name != "nt":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_char_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.lpDesktop = r"WinSta0\Default"
        si.dwFlags = 0x00000001  # STARTF_USESHOWWINDOW
        si.wShowWindow = 1       # SW_SHOWNORMAL
        pi = PROCESS_INFORMATION()

        success = ctypes.windll.kernel32.CreateProcessW(
            None,
            cmd,
            None,
            None,
            False,
            0x00000200,  # CREATE_NEW_PROCESS_GROUP
            None,
            cwd,
            ctypes.byref(si),
            ctypes.byref(pi),
        )
        if success:
            ctypes.windll.kernel32.CloseHandle(pi.hProcess)
            ctypes.windll.kernel32.CloseHandle(pi.hThread)
            return True
    except Exception as e:
        logger.warning(f"spawn_interactive_desktop_process failed: {e}")
    return False


@mcp.tool()
def launch_ymm4_desktop(project_dir: str) -> Dict[str, Any]:
    """Locates YMM4 and launches the project .ymmp file."""
    proj_path = workspace_path(project_dir)

    ymm4_path = find_ymm4_executable()
    if not ymm4_path or not os.path.exists(ymm4_path):
        raise FileNotFoundError(
            "Could not find YukkuriMovieMaker.exe. "
            "Please ensure YMM4 is in Documents, AppData, or Program Files, or set the YMM4_PATH environment variable."
        )

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

    ymm4_dir = str(Path(ymm4_path).parent)
    resolved_ymmp = str(ymmp_file.resolve())

    started = False
    ymm4_cmd = f'"{ymm4_path}" "{resolved_ymmp}"'
    if os.name == "nt":
        started = spawn_interactive_desktop_process(ymm4_cmd, cwd=ymm4_dir)

    if not started:
        kwargs: Dict[str, Any] = {
            "cwd": ymm4_dir,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        cmd = [ymm4_path, resolved_ymmp]
        try:
            subprocess.Popen(cmd, **kwargs)
            started = True
        except Exception as e:
            raise RuntimeError(f"Failed to launch YMM4: {e}")

    if os.name == "nt":
        explorer_cmd = f'explorer.exe /select,"{resolved_ymmp}"'
        if not spawn_interactive_desktop_process(explorer_cmd, cwd=ymm4_dir):
            try:
                subprocess.Popen(["explorer.exe", f"/select,{resolved_ymmp}"])
            except Exception:
                pass

    return {
        "launched": True,
        "executable": ymm4_path,
        "project": resolved_ymmp,
    }



@mcp.tool()
def list_projects() -> Dict[str, Any]:
    """Scans projects/ directory and returns available project folders with artifact flags."""
    projects_dir = Path.cwd() / "projects"
    if not projects_dir.exists():
        return {"projects": []}

    projects = []
    for proj_path in projects_dir.iterdir():
        if proj_path.is_dir():
            has_script = (proj_path / "script.json").exists()
            has_broll_manifest = (proj_path / "broll_manifest.json").exists()
            has_qa_video = (proj_path / "qa_test.mp4").exists()
            has_thumbnail = (proj_path / "thumbnail.png").exists()
            projects.append({
                "name": proj_path.name,
                "path": str(proj_path.relative_to(Path.cwd())),
                "has_script": has_script,
                "has_broll_manifest": has_broll_manifest,
                "has_qa_video": has_qa_video,
                "has_thumbnail": has_thumbnail
            })
    return {"projects": projects}

@mcp.tool()
def load_project(project_dir: str) -> Dict[str, Any]:
    """Resolves project_dir and returns parsed script, broll_manifest, and artifact paths."""
    proj_path = workspace_path(project_dir)

    script = []
    script_path = proj_path / "script.json"
    if script_path.exists():
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read script.json in {project_dir}: {e}")

    broll_manifest = []
    broll_path = proj_path / "broll_manifest.json"
    if broll_path.exists():
        try:
            with open(broll_path, "r", encoding="utf-8") as f:
                broll_manifest = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read broll_manifest.json in {project_dir}: {e}")

    qa_video_path = proj_path / "qa_test.mp4"
    thumbnail_path = proj_path / "thumbnail.png"
    ymmp_path = proj_path / "ymmp" / "final_video.ymmp"
    if not ymmp_path.exists():
        # Fallback to loose ymmp if it exists
        ymmps = list(proj_path.glob("*.ymmp"))
        if ymmps:
            ymmp_path = ymmps[0]

    premiere_xml = proj_path / "premiere" / f"{proj_path.name}.xml"
    if not premiere_xml.exists():
        # Fallback to final_video.xml
        alt_xml = proj_path / "premiere" / "final_video.xml"
        if alt_xml.exists():
            premiere_xml = alt_xml

    return {
        "script": script,
        "broll_manifest": broll_manifest,
        "qa_video_path": str(qa_video_path) if qa_video_path.exists() else None,
        "thumbnail_path": str(thumbnail_path) if thumbnail_path.exists() else None,
        "ymmp_path": str(ymmp_path) if ymmp_path.exists() else None,
        "premiere_xml": str(premiere_xml) if premiere_xml.exists() else None,
    }



@mcp.tool()
def save_project_script(project_dir: str, script_json: str, broll_manifest_json: Optional[str] = None) -> Dict[str, Any]:
    """Validates and writes script.json and optionally broll_manifest.json to project_dir."""
    proj_path = workspace_path(project_dir)
    proj_path.mkdir(parents=True, exist_ok=True)

    errors = []
    try:
        script_data = json.loads(script_json)
    except Exception as e:
        errors.append(f"Invalid JSON: {e}")
        script_data = None

    if script_data is not None:
        try:
            from veraxi_ymmp.script import validate_director_script, VALID_EMOTIONS
            # Heuristics check
            for idx, entry in enumerate(script_data):
                if not isinstance(entry, dict):
                    continue
                if "type" in entry and "character" not in entry:
                    continue

                char = entry.get("character", "unknown")
                text = entry.get("text", "")
                if isinstance(text, str) and len(text) > 40:
                    errors.append(f"Cut #{idx} ({char}): Exceeds 40 characters ({len(text)} chars).")

                emotion = entry.get("emotion")
                if emotion is not None and emotion not in VALID_EMOTIONS:
                    errors.append(f"Cut #{idx} ({char}): Invalid emotion '{emotion}'. Valid emotions are: [{', '.join(VALID_EMOTIONS)}]")

            validate_director_script(script_data)
        except Exception as e:
            if str(e) not in errors:
                errors.append(str(e))

    if errors:
        lines = [
            "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================",
            "The script you provided failed schema validation with the following errors:"
        ]
        for error in errors:
            lines.append(f"  - {error}")
        lines.append("Please fix these specific entries while preserving the rest of the script, and return the complete corrected JSON block.")
        lines.append("==========================================================================")
        reprompt = "\n".join(lines)
        return {
            "success": False,
            "valid": False,
            "errors": errors,
            "reprompt_block": reprompt
        }

    validation = validate_script(script_json)

    warnings = []
    for i, entry in enumerate(validation.get("entries", [])):
        text = entry.get("text", "")
        if len(text) > 35:
            warnings.append(f"Cut {i} ({entry.get('character')}) exceeds 35 characters ({len(text)}). Consider splitting.")

    from veraxi_ymmp.history import backup_project_script, cleanup_stale_audio

    # Non-destructive automatic revision backup before overriding
    backup_id = backup_project_script(proj_path, reason="script_save")

    with open(proj_path / "script.json", "w", encoding="utf-8") as f:
        f.write(script_json)

    if broll_manifest_json:
        try:
            # just basic validation
            parsed_broll = json.loads(broll_manifest_json)
            with open(proj_path / "broll_manifest.json", "w", encoding="utf-8") as f:
                json.dump(parsed_broll, f, ensure_ascii=False, indent=2)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid broll_manifest_json: {e}")

    cut_count = len(script_data) if isinstance(script_data, list) else 0
    cleaned_audio_count = cleanup_stale_audio(proj_path, cut_count)

    return {
        "success": True,
        "backup_created": backup_id,
        "cleaned_audio_count": cleaned_audio_count,
        "warnings": warnings
    }

@mcp.tool()
def list_project_history(project_dir: str) -> Dict[str, Any]:
    """Returns list of all timestamped historical backups of script.json for project_dir."""
    from veraxi_ymmp.history import list_script_history
    proj_path = workspace_path(project_dir)
    snapshots = list_script_history(proj_path)
    return {"project_dir": project_dir, "history": snapshots}

@mcp.tool()
def restore_project_history(project_dir: str, history_id: str) -> Dict[str, Any]:
    """Restores a previous historical script snapshot non-destructively (backing up current first)."""
    from veraxi_ymmp.history import restore_script_history
    proj_path = workspace_path(project_dir)
    return restore_script_history(proj_path, history_id)

@mcp.tool()
def upload_project_to_youtube(
    project_dir: str,
    title: str,
    privacy_status: str = "private",
    description: str = "",
    tags: Optional[List[str]] = None,
    publish_at: Optional[str] = None,
    mock_upload: bool = False
) -> Dict[str, Any]:
    """Uploads the project's video, thumbnail, and captions to YouTube."""
    proj_path = workspace_path(project_dir)

    candidates = ["final_video_youtube.mp4", "final_video.mp4", "qa_test.mp4"]
    target_video = None
    for cand in candidates:
        cand_path = proj_path / cand
        if cand_path.exists():
            target_video = cand_path
            break

    if not target_video:
        raise FileNotFoundError(f"No video artifact found in {proj_path} to upload.")

    thumbnail_path = proj_path / "thumbnail.png"
    if not thumbnail_path.exists():
        thumbnail_path = Path("")

    # Check for SRT captions
    captions = []
    for srt in proj_path.glob("*.srt"):
        captions.append({
            "path": srt,
            "language": "ja",
            "name": "日本語"
        })
        break # Just grab the first one for now

    if mock_upload:
        from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter
        publisher: Any = MockYouTubeAdapter(fail_upload=False)
    else:
        from veraxi_ymmp.youtube_adapter import YouTubeAdapter
        try:
            publisher = YouTubeAdapter()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize YouTube publisher (maybe needs auth): {e}")

    from veraxi_ymmp.ir import VideoPublishMetadata
    metadata = VideoPublishMetadata(
        title=title,
        description=description,
        tags=tags or [],
        privacy_status=privacy_status,
        publish_at=publish_at,
        thumbnail_path=thumbnail_path if thumbnail_path.exists() else None
    )

    result = publisher.upload_video(target_video, metadata)

    caption_uploaded = False
    if captions and hasattr(publisher, 'upload_caption'):
        try:
            publisher.upload_caption(result.video_id, Path(str(captions[0]["path"])), str(captions[0]["language"]), str(captions[0]["name"]))
            caption_uploaded = True
        except Exception as e:
            logger.warning(f"Failed to upload caption: {e}")

    return {
        "success": True,
        "video_id": result.video_id,
        "status": result.status,
        "thumbnail_uploaded": result.thumbnail_uploaded,
        "caption_uploaded": caption_uploaded,
        "bytes_uploaded": result.bytes_uploaded
    }



@mcp.tool()
def get_ai_prompt_spec() -> Dict[str, Any]:
    """Returns the Universal AI Prompt and JSON Schema for scripts."""
    from veraxi_ymmp.constants import DEFAULT_SPEAKER_MAP
    from veraxi_ymmp.schema import get_director_script_schema

    prompt_path = Path(__file__).parent / "templates" / "UNIVERSAL_AI_PROMPT.md"
    prompt_markdown = ""
    if prompt_path.exists():
        prompt_markdown = prompt_path.read_text(encoding="utf-8")

    # Append available speakers
    speakers_md = "\n\n### Available Speakers:\n"
    for name, spk_id in DEFAULT_SPEAKER_MAP.items():
        speakers_md += f"- **{name}** (ID: {spk_id})\n"

    prompt_markdown += speakers_md

    return {
        "prompt_markdown": prompt_markdown,
        "json_schema": get_director_script_schema()
    }


if __name__ == "__main__":
    mcp.run()
