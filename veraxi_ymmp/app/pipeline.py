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
from typing import Any, Dict, List, Optional, Union, cast

from veraxi_ymmp.app.compiler import YMMPCompiler
from veraxi_ymmp.core.ir import TimelineIR, UploadResult, VideoPublishMetadata
from veraxi_ymmp.core.logging import logger
from veraxi_ymmp.exporters.moviepy_renderer import MoviePyRenderer
from veraxi_ymmp.core.ports import VideoPublisher, PipelineProgressCallback
from veraxi_ymmp.exporters.premiere_exporter import PremiereExporter, export_to_premiere as export_to_premiere
from veraxi_ymmp.exporters.srt_generator import generate_srt
from veraxi_ymmp.graphics.thumbnail import generate_project_thumbnail
from veraxi_ymmp.exporters.ymmp_utils import validate_ymmp_timeline
from veraxi_ymmp.audio.voicevox import VoicevoxClient

try:
    from veraxi_ymmp.core.constants import DEFAULT_SPEAKER_MAP
except ImportError:
    DEFAULT_SPEAKER_MAP = {
        "ずんだもん": 3,
        "四国めたん": 2,
        "春日部つむぎ": 8,
    }

try:
    from veraxi_ymmp.core.script import validate_production_script
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
    final_video_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None
    srt_path: Optional[Path] = None
    upload_result: Optional[UploadResult] = None
    pacing_report: Optional[Any] = None
    fact_audit_outcome: Optional[Any] = None
    success: bool = True
    errors: List[str] = field(default_factory=list)


@dataclass
class _RunContext:
    """Mutable state shared by the ProjectPipeline.run stage functions.

    ``run`` is a thin sequencer; each ``_stage_*`` method performs one stage
    and reads/writes the fields it needs here instead of threading dozens of
    locals through the old 495-line monolith.
    """

    project_path: Union[str, Path]
    do_premiere: bool = True
    do_ymmp: bool = True
    do_qa: bool = True
    render_video: bool = False
    qa_duration: Optional[float] = None
    do_thumbnail: bool = True
    upload_to_youtube: bool = False
    mock_upload: bool = False
    publish_at: Optional[str] = None
    privacy_status: str = "private"
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    language: str = "ja"
    normalize_loudness: bool = False
    publisher: Optional[VideoPublisher] = None
    allow_synthetic: bool = False
    allow_unverified: bool = False
    verify_urls: bool = False
    # Stage outputs, filled in as the sequencer advances.
    proj_dir: Path = Path(".")
    result: PipelineResult = field(
        default_factory=lambda: PipelineResult(project_dir=Path("."))
    )
    script_path: Path = Path("script.json")
    script_data: Any = None
    broll_manifest_path: Path = Path("broll_manifest.json")
    compiler: Optional[YMMPCompiler] = None
    timeline_ir: Optional[TimelineIR] = None
    audio_files: List[Path] = field(default_factory=list)



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

    def _resolve_project_template(self, proj_dir: Path) -> Path:
        if self.template_path == Path("examples/full_template.ymmp"):
            from veraxi_ymmp.graphics.broll import detect_project_vertical
            shorts_tmpl = Path("examples/shorts_template.ymmp")
            if shorts_tmpl.exists() and detect_project_vertical(proj_dir):
                return shorts_tmpl
        return self.template_path

    def _notify(self, stage: str, progress: float, message: str) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(stage, progress, message)
            except Exception as cb_err:
                logger.debug(f"Progress callback raised an unhandled exception: {cb_err}")

    def run(
        self,
        project_path: Union[str, Path],
        do_premiere: bool = True,
        do_ymmp: bool = True,
        do_qa: bool = True,
        render_video: bool = False,
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
        allow_synthetic: bool = False,
        allow_unverified: bool = False,
        verify_urls: bool = False,
    ) -> PipelineResult:
        """Execute the end-to-end video synthesis pipeline for a project directory."""
        """Execute the end-to-end pipeline: a thin sequencer over the _stage_* methods."""
        ctx = _RunContext(
            project_path=project_path,
            do_premiere=do_premiere,
            do_ymmp=do_ymmp,
            do_qa=do_qa,
            render_video=render_video,
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
            allow_synthetic=allow_synthetic,
            allow_unverified=allow_unverified,
            verify_urls=verify_urls,
        )
        if not self._stage_load_script(ctx):
            return ctx.result
        self._stage_preflight(ctx)
        self._stage_setup_compiler(ctx)
        if not self._stage_gates(ctx):
            return ctx.result
        if not self._stage_build_ir(ctx):
            return ctx.result
        self._stage_export_premiere(ctx)
        self._stage_export_ymmp(ctx)
        self._stage_render_qa(ctx)
        self._stage_render_master(ctx)
        self._stage_thumbnail(ctx)
        if not self._stage_upload(ctx):
            return ctx.result
        if ctx.result.errors:
            ctx.result.success = False

        logger.info(f"Project '{ctx.proj_dir.name}' Execution Finished!")
        return ctx.result


    def _stage_load_script(self, ctx: _RunContext) -> bool:
        """Resolve the project, load and validate script.json. False = abort."""
        ctx.proj_dir = Path(ctx.project_path).resolve()
        ctx.result = PipelineResult(project_dir=ctx.proj_dir)

        if not ctx.proj_dir.exists():
            err_msg = f"Project directory '{ctx.project_path}' does not exist."
            logger.error(err_msg)
            ctx.result.errors.append(err_msg)
            ctx.result.success = False
            return False

        ctx.script_path = ctx.proj_dir / "script.json"
        if not ctx.script_path.exists():
            err_msg = f"No script.json found in '{ctx.project_path}'."
            logger.error(err_msg)
            ctx.result.errors.append(err_msg)
            ctx.result.success = False
            return False

        logger.info(f"Running Veraxi YMMP Project: {ctx.proj_dir.name} ({ctx.proj_dir})")

        try:
            ctx.script_data = json.loads(ctx.script_path.read_text(encoding="utf-8-sig"))
            logger.info(f"Loaded script: {len(ctx.script_data)} lines.")
        except Exception as e:
            err_msg = f"Failed to parse script.json: {e}"
            logger.error(err_msg)
            ctx.result.errors.append(err_msg)
            ctx.result.success = False
            return False

        validator = validate_production_script
        if validator is None:
            from veraxi_ymmp.core import script as _script_mod

            validator = getattr(_script_mod, "validate_production_script", None)
        if validator is not None:
            try:
                validator(ctx.script_data)
            except ValueError as e:
                logger.warning(f"Production script validation warning: {e}")

        return True

    def _stage_preflight(self, ctx: _RunContext) -> None:
        """Pacing preflight and the first B-Roll manifest pass."""
        # Audience Retention Pacing Preflight
        try:
            from veraxi_ymmp.editorial.pacing import audit_script_pacing
            pacing_report = audit_script_pacing(ctx.script_data)
            ctx.result.pacing_report = pacing_report
            logger.info(
                f"Audience Retention Pacing: Score {pacing_report.retention_score}/100 "
                f"({pacing_report.num_characters} characters, healthy={pacing_report.is_healthy})"
            )
            for v in pacing_report.violations:
                if v.severity in {"ERROR", "WARNING"}:
                    logger.warning(f"[{v.rule_name}] {v.message} (Remedy: {v.remedy})")
        except Exception as e:
            logger.debug(f"Pacing preflight skipped: {e}")

        # Optional B-Roll manifest pre-step
        ctx.broll_manifest_path = ctx.proj_dir / "broll_manifest.json"
        if ctx.broll_manifest_path.exists():
            logger.info("Found broll_manifest.json; rendering B-Roll assets...")
            try:
                from veraxi_ymmp.graphics.broll import render_from_manifest
                render_from_manifest(ctx.broll_manifest_path, ctx.proj_dir / "broll")
            except Exception as e:
                logger.warning(f"Failed rendering B-Roll manifest: {e}")

    def _stage_setup_compiler(self, ctx: _RunContext) -> None:
        """Initialise the TTS backend and compiler; second B-Roll pass."""
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

        ctx.compiler = YMMPCompiler(
            template_path=self._resolve_project_template(ctx.proj_dir),
            voicevox_client=backend if isinstance(backend, VoicevoxClient) else self.voicevox_client,
            tts_backend=backend,
            speaker_map=self.speaker_map,
        )
        if not self.use_tts:
            cast(YMMPCompiler, ctx.compiler).config.use_tts = False

        # Optional B-Roll manifest pre-step
        ctx.broll_manifest_path = ctx.proj_dir / "broll_manifest.json"
        if ctx.broll_manifest_path.exists():
            self._notify("rendering_broll", 0.05, "Rendering B-Roll slides from manifest...")
            try:
                from veraxi_ymmp.graphics.broll import render_from_manifest
                render_from_manifest(ctx.broll_manifest_path, ctx.proj_dir / "broll")
                self._notify("rendering_broll", 0.10, "B-Roll slides rendered successfully.")
            except Exception as e:
                logger.warning(f"Failed rendering B-Roll manifest: {e}")
                self._notify("rendering_broll", 0.10, f"B-Roll rendering skipped: {e}")
        else:
            # If no B-Roll manifest exists, advance progress smoothly so the GUI doesn't stall
            self._notify("rendering_broll", 0.10, "No B-Roll manifest found, skipping.")

    def _stage_gates(self, ctx: _RunContext) -> bool:
        """Fail-closed asset provenance and fact-ledger gates. False = abort."""
        # Fail-closed asset provenance & cryptographic verification guard
        try:
            from veraxi_ymmp.epistemic.asset_guard import verify_project_assets

            broll_data = None
            if ctx.broll_manifest_path.exists():
                try:
                    with open(ctx.broll_manifest_path, "r", encoding="utf-8-sig") as f:
                        broll_data = json.load(f)
                except Exception:
                    broll_data = None

            verify_project_assets(
                project_dir=ctx.proj_dir,
                script_entries=ctx.script_data if isinstance(ctx.script_data, list) else None,
                broll_manifest=broll_data,
                allow_synthetic=ctx.allow_synthetic,
            )
        except Exception as guard_err:
            logger.error(f"Asset integrity check failed: {guard_err}")
            ctx.result.errors.append(str(guard_err))
            ctx.result.success = False
            return False

        # Fail-closed Fact Ledger Audit & Quote Verification Gate
        claims_path = ctx.proj_dir / "claims.json"
        if not claims_path.is_file():
            if not ctx.allow_unverified:
                err_msg = (
                    f"Fact-check gate failed: No claim ledger found at '{claims_path}'. "
                    f"Every production project must have a claims.json (pass allow_unverified=True or --allow-unverified to bypass)."
                )
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)
                ctx.result.success = False
                return False
            else:
                logger.warning("Fact-check gate bypassed: No claims.json found, but allow_unverified=True.")
        else:
            try:
                from veraxi_ymmp.epistemic.fact_audit import audit_project_facts

                outcome = audit_project_facts(ctx.script_path, title=ctx.proj_dir.name, verify_urls=ctx.verify_urls)
                ctx.result.fact_audit_outcome = outcome
                if outcome.blocked and not ctx.allow_unverified:
                    err_msg = f"Fact-check gate blocked project execution ({len(outcome.blockers)} blockers in claims.json):"
                    logger.error(err_msg)
                    ctx.result.errors.append(err_msg)
                    for b in outcome.blockers:
                        b_detail = f"[FACTS] {b.claim.id} (cut {b.claim.cut_index}) {b.verdict.value}: {b.reason}"
                        logger.error(f"  - {b_detail}")
                        ctx.result.errors.append(b_detail)
                    ctx.result.success = False
                    return False
                elif outcome.blocked and ctx.allow_unverified:
                    logger.warning(
                        f"Fact-check gate has {len(outcome.blockers)} blockers, but overridden by allow_unverified=True."
                    )
            except Exception as fact_err:
                logger.error(f"Fact audit failed with error: {fact_err}")
                ctx.result.errors.append(f"Fact audit error: {fact_err}")
                ctx.result.success = False
                return False



        return True

    def _stage_build_ir(self, ctx: _RunContext) -> bool:
        """TTS synthesis and TimelineIR build (the 'tts' / IR stage). False = abort."""
        audio_dir = ctx.proj_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Building Timeline IR & Synthesizing Audio...")
        self._notify("synthesizing_audio", 0.15, f"Synthesizing voice audio for {len(ctx.script_data)} lines via VOICEVOX...")
        try:
            compiler = cast(YMMPCompiler, ctx.compiler)
            ctx.timeline_ir, ctx.audio_files = compiler.build_ir(ctx.script_data, audio_dir)
            ctx.result.timeline_ir = ctx.timeline_ir
            ctx.result.audio_files = ctx.audio_files
            logger.info(f"Synthesized {len(ctx.timeline_ir.voice_clips)} voice clips successfully.")
            self._notify(
                "synthesizing_audio",
                0.40,
                f"Synthesized {len(ctx.timeline_ir.voice_clips)} audio clips successfully.",
            )
        except Exception as e:
            err_msg = f"Failed during IR compilation: {e}"
            logger.error(err_msg)
            self._notify("synthesizing_audio", 0.40, f"Error synthesizing audio: {e}")
            ctx.result.errors.append(err_msg)
            ctx.result.success = False
            return False

        return True

    def _stage_export_premiere(self, ctx: _RunContext) -> None:
        """Premiere Pro FCPXML export."""
        timeline_ir = cast(TimelineIR, ctx.timeline_ir)
        # 2. Premiere Pro XML Export
        if ctx.do_premiere:
            logger.info("--- [1/3] Generating Premiere Pro FCPXML ---")
            try:
                premiere_dir = ctx.proj_dir / "premiere"
                premiere_dir.mkdir(parents=True, exist_ok=True)
                xml_out = premiere_dir / f"{ctx.proj_dir.name}.xml"
                premiere_exporter = self.exporters.get("premiere") if self.exporters else None
                if premiere_exporter is not None:
                    exported_xml = premiere_exporter.export(
                        timeline_ir,
                        xml_out,
                        options={"project_name": ctx.proj_dir.name, "output_dir": premiere_dir},
                    )
                else:
                    exported_xml = PremiereExporter(timeline_ir).export(
                        timeline_ir,
                        xml_out,
                        options={"project_name": ctx.proj_dir.name, "output_dir": premiere_dir},
                    )
                if hasattr(exported_xml, "output_path"):
                    xml_path = Path(exported_xml.output_path)
                elif exported_xml:
                    xml_path = Path(exported_xml)
                else:
                    xml_path = xml_out
                ctx.result.premiere_xml = xml_path
                logger.info(f"Premiere XML generated at: {xml_path}")
            except Exception as e:
                err_msg = f"Failed generating Premiere Pro XML: {e}"
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)

    def _stage_export_ymmp(self, ctx: _RunContext) -> None:
        """YMM4 .ymmp export and timeline validation."""
        timeline_ir = cast(TimelineIR, ctx.timeline_ir)
        compiler = cast(YMMPCompiler, ctx.compiler)
        # 3. YMM4 Project Export
        if ctx.do_ymmp:
            self._notify("exporting_ymmp_and_xml", 0.60, "Exporting YMMP")
            logger.info("--- [2/3] Generating Yukkuri Movie Maker 4 (.ymmp) ---")
            try:
                ymmp_dir = ctx.proj_dir / "ymmp"
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
                        require_audio=self.use_tts,
                    )
                    ctx.result.ymmp_validation = v_res
                ctx.result.ymmp_path = ymmp_out
                logger.info(f"YMM4 project generated at: {ymmp_out}")
            except Exception as e:
                err_msg = f"Failed generating YMM4 project: {e}"
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)

    def _stage_render_qa(self, ctx: _RunContext) -> None:
        """MoviePy QA preview render."""
        timeline_ir = cast(TimelineIR, ctx.timeline_ir)
        # 4. MoviePy QA Video
        if ctx.do_qa and not ctx.render_video:
            target_qa_duration = (
                ctx.qa_duration if ctx.qa_duration is not None else self.fast_qa_duration
            )
            effective_qa_duration = target_qa_duration
            if effective_qa_duration is not None and hasattr(
                timeline_ir, "min_all_speakers_duration"
            ):
                effective_qa_duration = timeline_ir.min_all_speakers_duration(
                    effective_qa_duration
                )
            self._notify("exporting_ymmp_and_xml", 0.70, "YMMP Export Complete")
            self._notify("moviepy_rendering", 0.70, "Rendering QA")
            logger.info(
                f"--- [3/4] Rendering MoviePy QA Preview Video ({effective_qa_duration}s) ---"
            )
            try:
                qa_out = ctx.proj_dir / "qa_test.mp4"
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
                ctx.result.qa_video_path = qa_out
                logger.info(f"QA preview video ready at: {qa_out}")
                self._notify("moviepy_rendering", 0.85, "QA Render Complete")
            except Exception as e:
                err_msg = f"Failed generating MoviePy QA video: {e}"
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)

    def _stage_render_master(self, ctx: _RunContext) -> None:
        """Headless production master render."""
        timeline_ir = cast(TimelineIR, ctx.timeline_ir)
        if ctx.render_video:
            self._notify("exporting_ymmp_and_xml", 0.70, "YMMP Export Complete")
            self._notify("production_rendering", 0.70, "Rendering Production Master Video")
            logger.info("--- Headless Production Video Rendering ---")
            try:
                master_video_path = ctx.proj_dir / "final_video.mp4"
                exporter = (
                    (self.exporters.get("production") or self.exporters.get("moviepy"))
                    if self.exporters
                    else None
                )
                if exporter is None:
                    exporter = MoviePyRenderer(timeline_ir)
                exporter.export(
                    timeline_ir,
                    master_video_path,
                    options={
                        "preset": "medium",
                        "crf": 18,
                        "fast_qa_duration": None,
                        "normalize_loudness": ctx.normalize_loudness,
                    },
                )
                ctx.result.final_video_path = master_video_path
                ctx.result.qa_video_path = master_video_path
                logger.info(f"Production video ready at: {master_video_path}")
                self._notify("production_rendering", 0.85, "Production Video Complete")
            except Exception as e:
                err_msg = f"Failed generating Production video: {e}"
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)

    def _stage_thumbnail(self, ctx: _RunContext) -> None:
        """YouTube thumbnail and metadata text."""
        # 5. High-CTR YouTube Thumbnail
        if ctx.do_thumbnail:
            logger.info("--- [4/4] Generating High-CTR YouTube Thumbnail ---")
            try:
                thumb_out = ctx.proj_dir / "thumbnail.png"
                generate_project_thumbnail(ctx.proj_dir, out_path=thumb_out)
                ctx.result.thumbnail_path = thumb_out
                logger.info(f"High-CTR YouTube thumbnail ready at: {thumb_out}")
            except Exception as e:
                err_msg = f"Failed generating thumbnail: {e}"
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)

        # 5b. Copy-paste YouTube ctx.title / ctx.description / credits (youtube_metadata.txt)
        try:
            from veraxi_ymmp.exporters.youtube_metadata import generate_project_youtube_metadata

            generate_project_youtube_metadata(ctx.proj_dir, timeline_ir=ctx.result.timeline_ir)
            logger.info(f"YouTube metadata ready at: {ctx.proj_dir / 'youtube_metadata.txt'}")
        except Exception as e:
            logger.warning(f"Failed generating YouTube metadata: {e}")

    def _stage_upload(self, ctx: _RunContext) -> bool:
        """YouTube publishing automation. False = abort (no video artifact)."""
        # 6. YouTube Publishing Automation
        if ctx.upload_to_youtube:
            logger.info("--- [5/5] YouTube Publishing Automation ---")
            target_video: Optional[Path] = None
            final_video_candidate = ctx.proj_dir / "final_video.mp4"
            if ctx.result.final_video_path and ctx.result.final_video_path.exists():
                target_video = ctx.result.final_video_path
            elif final_video_candidate.exists():
                target_video = final_video_candidate
            elif ctx.result.qa_video_path and ctx.result.qa_video_path.exists():
                target_video = ctx.result.qa_video_path

            if target_video is None:
                err_msg = "No video artifact found for YouTube upload (checked final_video.mp4 and qa_test.mp4)."
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)
                ctx.result.success = False
                return False

            if ctx.result.thumbnail_path is None:
                default_thumb = ctx.proj_dir / "thumbnail.png"
                if default_thumb.exists():
                    ctx.result.thumbnail_path = default_thumb

            video_to_upload = target_video
            if ctx.normalize_loudness and not ctx.render_video:
                self._notify("audio_normalization", 0.85, "Normalizing Audio")
                logger.info("Normalizing video audio loudness for YouTube (-14.0 LUFS)...")
                from veraxi_ymmp.audio.audio_normalizer import normalize_video_audio

                norm_out = ctx.proj_dir / f"{target_video.stem}_normalized{target_video.suffix}"
                try:
                    video_to_upload = normalize_video_audio(target_video, norm_out, target_i=-14.0)
                    logger.info(f"Loudness normalized video ready: {video_to_upload}")
                    self._notify("audio_normalization", 0.95, "Normalization Complete")
                except Exception as e:
                    logger.warning(f"Loudness normalization failed, using original video: {e}")
                    video_to_upload = target_video

            if ctx.result.timeline_ir is not None:
                logger.info("Auto-generating SRT captions from TimelineIR...")
                srt_out = ctx.proj_dir / f"{ctx.proj_dir.name}.srt"
                try:
                    generate_srt(ctx.result.timeline_ir, srt_out)
                    ctx.result.srt_path = srt_out
                    logger.info(f"SRT captions generated at: {srt_out}")
                except Exception as e:
                    logger.warning(f"Failed to generate SRT captions: {e}")

            pub: VideoPublisher
            if ctx.publisher is not None:
                pub = ctx.publisher
            elif ctx.mock_upload:
                from veraxi_ymmp.exporters.youtube_adapter import MockYouTubeAdapter

                pub = MockYouTubeAdapter()
            else:
                from veraxi_ymmp.exporters.youtube_adapter import YouTubeAdapter

                pub = YouTubeAdapter()

            try:
                meta = VideoPublishMetadata(
                    title=ctx.title or ctx.proj_dir.name,
                    description=ctx.description or "",
                    tags=ctx.tags or [],
                    category_id="22",
                    privacy_status=ctx.privacy_status,
                    publish_at=ctx.publish_at,
                    language=ctx.language,
                    thumbnail_path=ctx.result.thumbnail_path,
                )
                upload_res = pub.upload_video(video_path=video_to_upload, metadata=meta)
                ctx.result.upload_result = upload_res

                if upload_res.status in ("completed", "uploaded"):
                    if ctx.result.thumbnail_path and ctx.result.thumbnail_path.exists() and not upload_res.thumbnail_uploaded:
                        try:
                            pub.upload_thumbnail(upload_res.video_id, ctx.result.thumbnail_path)
                            upload_res.thumbnail_uploaded = True
                            logger.info(f"Thumbnail uploaded for video {upload_res.video_id}")
                        except Exception as e:
                            logger.warning(f"Failed to upload thumbnail: {e}")
                    if ctx.result.srt_path and ctx.result.srt_path.exists():
                        try:
                            pub.upload_caption(
                                upload_res.video_id,
                                ctx.result.srt_path,
                                language=ctx.language,
                                name="Japanese",
                            )
                            logger.info(f"Captions uploaded for video {upload_res.video_id}")
                        except Exception as e:
                            logger.warning(f"Failed to upload captions: {e}")
                else:
                    err_msg = f"YouTube upload failed: {upload_res.error_message or upload_res.status}"
                    logger.error(err_msg)
                    ctx.result.errors.append(err_msg)
                    ctx.result.success = False
            except Exception as e:
                err_msg = f"Failed during YouTube upload: {e}"
                logger.error(err_msg)
                ctx.result.errors.append(err_msg)
                ctx.result.success = False

        return True


def run_project(
    project_path: Union[str, Path],
    do_premiere: bool = True,
    do_ymmp: bool = True,
    do_qa: bool = True,
    render_video: bool = False,
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
    allow_synthetic: bool = False,
    allow_unverified: bool = False,
) -> PipelineResult:
    """Convenience function running ProjectPipeline for a project directory."""
    pipeline = ProjectPipeline()
    return pipeline.run(
        project_path=project_path,
        do_premiere=do_premiere,
        do_ymmp=do_ymmp,
        do_qa=do_qa,
        render_video=render_video,
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
        allow_synthetic=allow_synthetic,
        allow_unverified=allow_unverified,
    )


__all__ = [
    "PipelineResult",
    "ProjectPipeline",
    "run_project",
]
