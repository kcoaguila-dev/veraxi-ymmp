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
from .ir import TimelineIR, UploadResult, VideoPublishMetadata
from .logging import logger
from .moviepy_renderer import MoviePyRenderer
from .ports import VideoPublisher, PipelineProgressCallback
from .premiere_exporter import PremiereExporter, export_to_premiere as export_to_premiere
from .srt_generator import generate_srt
from .thumbnail import generate_project_thumbnail
from .validation import validate_ymmp_timeline
from .voicevox import VoicevoxClient

try:
    from .constants import DEFAULT_SPEAKER_MAP
except ImportError:
    DEFAULT_SPEAKER_MAP = {
        "ずんだもん": 3,
        "四国めたん": 2,
        "春日部つむぎ": 8,
    }

try:
    from .script import validate_production_script
except ImportError:
    validate_production_script = None  # type: ignore[assignment]


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
    srt_path: Optional[Path] = None
    upload_result: Optional[UploadResult] = None
    success: bool = True
    errors: List[str] = field(default_factory=list)


class ProjectPipeline:
    """End-to-end project orchestration pipeline for Veraxi YMMP."""

    def __init__(
        self,
        template_path: Union[str, Path] = "examples/full_template.ymmp",
        voicevox_client: Optional[VoicevoxClient] = None,
        speaker_map: Optional[Dict[str, int]] = None,
        use_tts: bool = True,
        fast_qa_duration: Optional[float] = 25.0,
        tts_backend: Optional[Any] = None,
        exporters: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[PipelineProgressCallback] = None,
    ) -> None:
        self.template_path = Path(template_path)
        self.voicevox_client = voicevox_client
        self.tts_backend = tts_backend or voicevox_client
        self.use_tts = use_tts
        self.speaker_map = (
            dict(speaker_map) if speaker_map is not None else dict(DEFAULT_SPEAKER_MAP)
        )
        self.fast_qa_duration = fast_qa_duration
        self.exporters = dict(exporters) if exporters is not None else {}
        self.progress_callback = progress_callback

    def run(
        self,
        project_path: Union[str, Path],
        do_premiere: bool = True,
        do_ymmp: bool = True,
        do_qa: bool = True,
        qa_duration: Optional[float] = None,
        do_thumbnail: bool = True,
        upload_to_youtube: bool = False,
        mock_upload: bool = False,
        publish_at: Optional[str] = None,
        privacy_status: str = "private",
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        language: str = "ja",
        normalize_loudness: bool = False,
        publisher: Optional[VideoPublisher] = None,
    ) -> PipelineResult:
        """Execute the end-to-end video synthesis pipeline for a project directory."""
        def _notify(stage: str, progress: float, message: str) -> None:
            if self.progress_callback:
                try:
                    self.progress_callback(stage, progress, message)
                except Exception as cb_err:
                    logger.debug(f"Progress callback raised an unhandled exception: {cb_err}")

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
            script_data = json.loads(script_path.read_text(encoding="utf-8-sig"))
            logger.info(f"Loaded script: {len(script_data)} lines.")
        except Exception as e:
            err_msg = f"Failed to parse script.json: {e}"
            logger.error(err_msg)
            result.errors.append(err_msg)
            result.success = False
            return result

        validator = validate_production_script
        if validator is None:
            from . import script as _script_mod

            validator = getattr(_script_mod, "validate_production_script", None)
        if validator is not None:
            try:
                validator(script_data)
            except ValueError as e:
                logger.warning(f"Production script validation warning: {e}")

        # Optional B-Roll manifest pre-step
        broll_manifest_path = proj_dir / "broll_manifest.json"
        if broll_manifest_path.exists():
            logger.info("Found broll_manifest.json; rendering B-Roll assets...")
            try:
                from .broll import render_from_manifest
                render_from_manifest(broll_manifest_path, proj_dir / "broll")
            except Exception as e:
                logger.warning(f"Failed rendering B-Roll manifest: {e}")

        # 1. Initialize TTS backend & build IR
        backend = self.tts_backend or self.voicevox_client
        if self.use_tts and backend is None:
            logger.info("Initializing Voicevox Client...")
            vv_candidate = VoicevoxClient()
            if vv_candidate.ensure_started():
                backend = vv_candidate
            else:
                logger.warning("VOICEVOX could not be started. Audio will not be generated.")
        elif not self.use_tts:
            backend = None

        compiler = YMMPCompiler(
            template_path=self.template_path,
            voicevox_client=backend if isinstance(backend, VoicevoxClient) else self.voicevox_client,
            tts_backend=backend,
            speaker_map=self.speaker_map,
        )
        if not self.use_tts:
            compiler.config.use_tts = False

        # Optional B-Roll manifest pre-step
        broll_manifest_path = proj_dir / "broll_manifest.json"
        if broll_manifest_path.exists():
            _notify("rendering_broll", 0.05, "Rendering B-Roll slides from manifest...")
            try:
                from .broll import render_from_manifest
                render_from_manifest(broll_manifest_path, proj_dir / "broll")
                _notify("rendering_broll", 0.10, "B-Roll slides rendered successfully.")
            except Exception as e:
                logger.warning(f"Failed rendering B-Roll manifest: {e}")
                _notify("rendering_broll", 0.10, f"B-Roll rendering skipped: {e}")
        else:
            # If no B-Roll manifest exists, advance progress smoothly so the GUI doesn't stall
            _notify("rendering_broll", 0.10, "No B-Roll manifest found, skipping.")

        audio_dir = proj_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Building Timeline IR & Synthesizing Audio...")
        _notify("synthesizing_audio", 0.15, f"Synthesizing voice audio for {len(script_data)} lines via VOICEVOX...")
        try:
            timeline_ir, audio_files = compiler.build_ir(script_data, audio_dir)
            result.timeline_ir = timeline_ir
            result.audio_files = audio_files
            logger.info(f"Synthesized {len(timeline_ir.voice_clips)} voice clips successfully.")
            _notify(
                "synthesizing_audio",
                0.40,
                f"Synthesized {len(timeline_ir.voice_clips)} audio clips successfully.",
            )
        except Exception as e:
            err_msg = f"Failed during IR compilation: {e}"
            logger.error(err_msg)
            _notify("synthesizing_audio", 0.40, f"Error synthesizing audio: {e}")
            result.errors.append(err_msg)
            result.success = False
            return result

        # 2. Premiere Pro XML Export
        if do_premiere:
            logger.info("--- [1/3] Generating Premiere Pro FCPXML ---")
            try:
                premiere_dir = proj_dir / "premiere"
                premiere_dir.mkdir(parents=True, exist_ok=True)
                xml_out = premiere_dir / f"{proj_dir.name}.xml"
                premiere_exporter = self.exporters.get("premiere") if self.exporters else None
                if premiere_exporter is not None:
                    exported_xml = premiere_exporter.export(
                        timeline_ir,
                        xml_out,
                        options={"project_name": proj_dir.name, "output_dir": premiere_dir},
                    )
                else:
                    exported_xml = PremiereExporter(timeline_ir).export(
                        timeline_ir,
                        xml_out,
                        options={"project_name": proj_dir.name, "output_dir": premiere_dir},
                    )
                if hasattr(exported_xml, "output_path"):
                    xml_path = Path(exported_xml.output_path)
                elif exported_xml:
                    xml_path = Path(exported_xml)
                else:
                    xml_path = xml_out
                result.premiere_xml = xml_path
                logger.info(f"Premiere XML generated at: {xml_path}")
            except Exception as e:
                err_msg = f"Failed generating Premiere Pro XML: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        # 3. YMM4 Project Export
        if do_ymmp:
            _notify("exporting_ymmp_and_xml", 0.60, "Exporting YMMP")
            logger.info("--- [2/3] Generating Yukkuri Movie Maker 4 (.ymmp) ---")
            try:
                ymmp_dir = proj_dir / "ymmp"
                ymmp_dir.mkdir(parents=True, exist_ok=True)
                ymmp_out = ymmp_dir / "final_video.ymmp"
                ymmp_exporter = self.exporters.get("ymmp") if self.exporters else None
                if ymmp_exporter is not None:
                    ymmp_exporter.export(timeline_ir, ymmp_out)
                else:
                    compiler._renderer.export(timeline_ir, ymmp_out)
                if ymmp_out.exists():
                    with open(ymmp_out, "r", encoding="utf-8-sig") as f:
                        v_data = json.load(f)
                    v_res = validate_ymmp_timeline(
                        v_data,
                        expected_voice_count=len(timeline_ir.voice_clips),
                    )
                    result.ymmp_validation = v_res
                result.ymmp_path = ymmp_out
                logger.info(f"YMM4 project generated at: {ymmp_out}")
            except Exception as e:
                err_msg = f"Failed generating YMM4 project: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)

        # 4. MoviePy QA Video
        if do_qa:
            target_qa_duration = (
                qa_duration if qa_duration is not None else self.fast_qa_duration
            )
            effective_qa_duration = target_qa_duration
            if effective_qa_duration is not None and hasattr(
                timeline_ir, "min_all_speakers_duration"
            ):
                effective_qa_duration = timeline_ir.min_all_speakers_duration(
                    effective_qa_duration
                )
            _notify("exporting_ymmp_and_xml", 0.70, "YMMP Export Complete")
            _notify("moviepy_rendering", 0.70, "Rendering QA")
            logger.info(
                f"--- [3/4] Rendering MoviePy QA Preview Video ({effective_qa_duration}s) ---"
            )
            try:
                qa_out = proj_dir / "qa_test.mp4"
                qa_exporter = (
                    (self.exporters.get("qa") or self.exporters.get("moviepy"))
                    if self.exporters
                    else None
                )
                if qa_exporter is not None:
                    qa_exporter.export(
                        timeline_ir,
                        qa_out,
                        options={"fast_qa_duration": effective_qa_duration},
                    )
                else:
                    MoviePyRenderer(
                        timeline_ir,
                        fast_qa_duration=effective_qa_duration,
                    ).export(
                        timeline_ir,
                        qa_out,
                        options={"fast_qa_duration": effective_qa_duration},
                    )
                result.qa_video_path = qa_out
                logger.info(f"QA preview video ready at: {qa_out}")
                _notify("moviepy_rendering", 0.85, "QA Render Complete")
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

        # 6. YouTube Publishing Automation
        if upload_to_youtube:
            logger.info("--- [5/5] YouTube Publishing Automation ---")
            target_video: Optional[Path] = None
            final_video_candidate = proj_dir / "final_video.mp4"
            if final_video_candidate.exists():
                target_video = final_video_candidate
            elif result.qa_video_path and result.qa_video_path.exists():
                target_video = result.qa_video_path

            if target_video is None:
                err_msg = "No video artifact found for YouTube upload (checked final_video.mp4 and qa_test.mp4)."
                logger.error(err_msg)
                result.errors.append(err_msg)
                result.success = False
                return result

            if result.thumbnail_path is None:
                default_thumb = proj_dir / "thumbnail.png"
                if default_thumb.exists():
                    result.thumbnail_path = default_thumb

            video_to_upload = target_video
            if normalize_loudness:
                _notify("audio_normalization", 0.85, "Normalizing Audio")
                logger.info("Normalizing video audio loudness for YouTube (-14.0 LUFS)...")
                from .audio_normalizer import normalize_video_audio

                norm_out = proj_dir / f"{target_video.stem}_normalized{target_video.suffix}"
                try:
                    video_to_upload = normalize_video_audio(target_video, norm_out, target_i=-14.0)
                    logger.info(f"Loudness normalized video ready: {video_to_upload}")
                    _notify("audio_normalization", 0.95, "Normalization Complete")
                except Exception as e:
                    logger.warning(f"Loudness normalization failed, using original video: {e}")
                    video_to_upload = target_video

            if result.timeline_ir is not None:
                logger.info("Auto-generating SRT captions from TimelineIR...")
                srt_out = proj_dir / f"{proj_dir.name}.srt"
                try:
                    generate_srt(result.timeline_ir, srt_out)
                    result.srt_path = srt_out
                    logger.info(f"SRT captions generated at: {srt_out}")
                except Exception as e:
                    logger.warning(f"Failed to generate SRT captions: {e}")

            pub: VideoPublisher
            if publisher is not None:
                pub = publisher
            elif mock_upload:
                from .youtube_adapter import MockYouTubeAdapter

                pub = MockYouTubeAdapter()
            else:
                from .youtube_adapter import YouTubeAdapter

                pub = YouTubeAdapter()

            try:
                meta = VideoPublishMetadata(
                    title=title or proj_dir.name,
                    description=description or "",
                    tags=tags or [],
                    category_id="22",
                    privacy_status=privacy_status,
                    publish_at=publish_at,
                    language=language,
                    thumbnail_path=result.thumbnail_path,
                )
                upload_res = pub.upload_video(video_path=video_to_upload, metadata=meta)
                result.upload_result = upload_res

                if upload_res.status in ("completed", "uploaded"):
                    if result.thumbnail_path and result.thumbnail_path.exists() and not upload_res.thumbnail_uploaded:
                        try:
                            pub.upload_thumbnail(upload_res.video_id, result.thumbnail_path)
                            upload_res.thumbnail_uploaded = True
                            logger.info(f"Thumbnail uploaded for video {upload_res.video_id}")
                        except Exception as e:
                            logger.warning(f"Failed to upload thumbnail: {e}")
                    if result.srt_path and result.srt_path.exists():
                        try:
                            pub.upload_caption(
                                upload_res.video_id,
                                result.srt_path,
                                language=language,
                                name="Japanese",
                            )
                            logger.info(f"Captions uploaded for video {upload_res.video_id}")
                        except Exception as e:
                            logger.warning(f"Failed to upload captions: {e}")
                else:
                    err_msg = f"YouTube upload failed: {upload_res.error_message or upload_res.status}"
                    logger.error(err_msg)
                    result.errors.append(err_msg)
                    result.success = False
            except Exception as e:
                err_msg = f"Failed during YouTube upload: {e}"
                logger.error(err_msg)
                result.errors.append(err_msg)
                result.success = False

        if result.errors:
            result.success = False

        logger.info(f"Project '{proj_dir.name}' Execution Finished!")
        return result


def run_project(
    project_path: Union[str, Path],
    do_premiere: bool = True,
    do_ymmp: bool = True,
    do_qa: bool = True,
    qa_duration: Optional[float] = None,
    do_thumbnail: bool = True,
    upload_to_youtube: bool = False,
    mock_upload: bool = False,
    publish_at: Optional[str] = None,
    privacy_status: str = "private",
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    language: str = "ja",
    normalize_loudness: bool = False,
    publisher: Optional[VideoPublisher] = None,
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
        upload_to_youtube=upload_to_youtube,
        mock_upload=mock_upload,
        publish_at=publish_at,
        privacy_status=privacy_status,
        title=title,
        description=description,
        tags=tags,
        language=language,
        normalize_loudness=normalize_loudness,
        publisher=publisher,
    )


__all__ = [
    "PipelineResult",
    "ProjectPipeline",
    "run_project",
]
