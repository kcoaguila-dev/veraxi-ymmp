"""
Application Service: ProjectPipeline.

Encapsulates the end-to-end video synthesis and multi-format export workflow:
Step 1: Audio synthesis & TimelineIR compilation
Step 2: Premiere Pro FCPXML export
Step 3: YMM4 .ymmp project export with strict QA validation
Step 4: Fast MoviePy MP4 QA preview render
Step 5: High-CTR YouTube thumbnail generation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .compiler import YMMPCompiler
from .ir import TimelineIR
from .logging import logger
from .moviepy_renderer import MoviePyRenderer
from .premiere_exporter import export_to_premiere
from .thumbnail import generate_project_thumbnail
from .validation import validate_ymmp_timeline
from .voicevox import VoicevoxClient


@dataclass
class PipelineResult:
    """Result of running an end-to-end project pipeline."""

    project_dir: Path
    timeline_ir: Optional[TimelineIR] = None
    audio_files: List[Path] = field(default_factory=list)
    premiere_xml: Optional[Path] = None
    ymmp_path: Optional[Path] = None
    ymmp_validation: Optional[Dict[str, Any]] = None
    qa_video_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None
    success: bool = True
    errors: List[str] = field(default_factory=list)


class ProjectPipeline:
    """End-to-end project orchestration pipeline for Veraxi YMMP."""

    def __init__(
        self,
        template_path: Union[str, Path] = "examples/full_template.ymmp",
        voicevox_client: Optional[VoicevoxClient] = None,
        speaker_map: Optional[Dict[str, int]] = None,
    ) -> None:
        self.template_path = Path(template_path)
        self.voicevox_client = voicevox_client
        self.speaker_map = speaker_map or {
            "ずんだもん": 3,
            "四国めたん": 2,
            "春日部つむぎ": 8,
        }

    def run(
        self,
        project_path: Union[str, Path],
        do_premiere: bool = True,
        do_ymmp: bool = True,
        do_qa: bool = True,
        qa_duration: float = 30.0,
        do_thumbnail: bool = True,
    ) -> PipelineResult:
        """Execute the end-to-end video synthesis pipeline for a project directory."""
        proj_dir = Path(project_path).resolve()
        result = PipelineResult(project_dir=proj_dir)

        if not proj_dir.exists():
            err_msg = f"Project directory '{project_path}' does not exist."
            logger.error(err_msg)
            result.errors.append(err_msg)
            result.success = False
            return result

        script_path = proj_dir / "script.json"
        if not script_path.exists():
            err_msg = f"No script.json found in '{project_path}'."
            logger.error(err_msg)
            result.errors.append(err_msg)
            result.success = False
            return result

        logger.info(f"Running Veraxi YMMP Project: {proj_dir.name} ({proj_dir})")

        try:
            script = json.loads(script_path.read_text(encoding="utf-8-sig"))
            logger.info(f"Loaded script: {len(script)} lines.")
        except Exception as e:
            err_msg = f"Failed to parse script.json: {e}"
            logger.error(err_msg)
            result.errors.append(err_msg)
            result.success = False
            return result

        # 1. Initialize Voicevox & build IR
        logger.info("Initializing Voicevox Client...")
        vv = self.voicevox_client
        if vv is None:
            vv_candidate = VoicevoxClient()
            if vv_candidate.ensure_started():
                vv = vv_candidate
            else:
                logger.warning("VOICEVOX could not be started. Audio will not be generated.")

        compiler = YMMPCompiler(
            template_path=self.template_path,
            voicevox_client=vv,
            speaker_map=self.speaker_map,
        )

        audio_dir = proj_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Building Timeline IR & Synthesizing Audio...")
        try:
            timeline_ir, audio_files = compiler.build_ir(script, audio_dir)
            result.timeline_ir = timeline_ir
            result.audio_files = audio_files
            logger.info(f"Synthesized {len(timeline_ir.voice_clips)} voice clips successfully.")
        except Exception as e:
            err_msg = f"Failed during IR compilation: {e}"
            logger.error(err_msg)
            result.errors.append(err_msg)
            result.success = False
            return result

        # 2. Premiere Pro XML Export
        if do_premiere:
            logger.info("--- [1/3] Generating Premiere Pro FCPXML ---")
            try:
                xml_dir = proj_dir / "premiere"
                proj_assets_dir = proj_dir / "premiere"
                xml_dir.mkdir(parents=True, exist_ok=True)
                res = export_to_premiere(
                    timeline_ir,
                    xml_dir,
                    proj_assets_dir,
                    xml_filename=f"{proj_dir.name}.xml",
                )
                xml_path = Path(res["xml_path"])
                result.premiere_xml = xml_path
                logger.info(f"Premiere XML generated at: {xml_path}")
            except Exception as e:
                err_msg = f"Failed generating Premiere Pro XML: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        # 3. YMM4 Project Export
        if do_ymmp:
            logger.info("--- [2/3] Generating Yukkuri Movie Maker 4 (.ymmp) ---")
            try:
                ymmp_dir = proj_dir / "ymmp"
                ymmp_dir.mkdir(parents=True, exist_ok=True)
                ymmp_out = ymmp_dir / "final_video.ymmp"
                compiler.render_ymmp(
                    timeline_ir,
                    ymmp_out,
                    False,
                    len(timeline_ir.voice_clips),
                    audio_files,
                )
                with open(ymmp_out, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                v_res = validate_ymmp_timeline(
                    v_data,
                    expected_voice_count=len(timeline_ir.voice_clips),
                )
                result.ymmp_path = ymmp_out
                result.ymmp_validation = v_res
                logger.info(f"YMM4 project generated at: {ymmp_out}")
            except Exception as e:
                err_msg = f"Failed generating YMM4 project: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        # 4. MoviePy QA Video
        if do_qa:
            logger.info(f"--- [3/4] Rendering MoviePy QA Preview Video ({qa_duration}s) ---")
            try:
                renderer = MoviePyRenderer(timeline_ir)
                renderer.fast_qa_duration = qa_duration
                qa_out = proj_dir / "qa_test.mp4"
                renderer.render(str(qa_out))
                result.qa_video_path = qa_out
                logger.info(f"QA preview video ready at: {qa_out}")
            except Exception as e:
                err_msg = f"Failed generating MoviePy QA video: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        # 5. High-CTR YouTube Thumbnail
        if do_thumbnail:
            logger.info("--- [4/4] Generating High-CTR YouTube Thumbnail ---")
            try:
                thumb_out = proj_dir / "thumbnail.png"
                generate_project_thumbnail(proj_dir, out_path=thumb_out)
                result.thumbnail_path = thumb_out
                logger.info(f"High-CTR YouTube thumbnail ready at: {thumb_out}")
            except Exception as e:
                err_msg = f"Failed generating thumbnail: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        if result.errors:
            result.success = False

        logger.info(f"Project '{proj_dir.name}' Execution Finished!")
        return result


def run_project(
    project_path: Union[str, Path],
    do_premiere: bool = True,
    do_ymmp: bool = True,
    do_qa: bool = True,
    qa_duration: float = 30.0,
    do_thumbnail: bool = True,
) -> PipelineResult:
    """Convenience function running ProjectPipeline for a project directory."""
    pipeline = ProjectPipeline()
    return pipeline.run(
        project_path=project_path,
        do_premiere=do_premiere,
        do_ymmp=do_ymmp,
        do_qa=do_qa,
        qa_duration=qa_duration,
        do_thumbnail=do_thumbnail,
    )


__all__ = [
    "PipelineResult",
    "ProjectPipeline",
    "run_project",
]
