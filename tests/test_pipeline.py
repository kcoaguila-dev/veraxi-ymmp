"""Unit tests for ProjectPipeline orchestration and multi-platform audio normalization."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from veraxi_ymmp.audio_normalizer import PLATFORM_TARGETS, normalize_all_platforms
from veraxi_ymmp.ir import TimelineIR, VoiceClip
from veraxi_ymmp.pipeline import ProjectPipeline, run_project
from veraxi_ymmp.ports import ExportResult


def test_pipeline_full_orchestration_with_mocked_exporters(tmp_path: Path) -> None:
    """ProjectPipeline.run orchestrates IR build, Premiere, YMMP, QA video, and thumbnail."""
    proj_dir = tmp_path / "sample_project"
    proj_dir.mkdir()

    script_file = proj_dir / "script.json"
    script_file.write_text(
        json.dumps([{"character": "ずんだもん", "text": "パイプラインのテストなのだ！"}], ensure_ascii=False),
        encoding="utf-8",
    )

    dummy_ir = TimelineIR(
        fps=60,
        total_frames=90,
        voice_clips=[
            VoiceClip(
                start_frame=0,
                length=90,
                character="ずんだもん",
                text="パイプラインのテストなのだ！",
                emotion="normal",
                motion="none",
                audio_path=None,
                hatsuon="パイプラインノテストナノダ",
                subtitle_position="bottom_center",
                subtitle_style="outlined",
            )
        ],
    )

    fake_xml = proj_dir / "premiere" / "sample_project.xml"
    fake_thumb = proj_dir / "thumbnail.png"

    mock_premiere_exp = MagicMock()
    mock_premiere_exp.export.return_value = str(fake_xml)

    mock_ymmp_exp = MagicMock()

    def _write_dummy_ymmp(ir: TimelineIR, out_path: Path, *args: object, **kwargs: object) -> ExportResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('{"Timeline": {"Items": []}}', encoding="utf-8")
        return ExportResult(target_format="ymmp", output_path=out_path)

    mock_ymmp_exp.export.side_effect = _write_dummy_ymmp

    mock_qa_exp = MagicMock()

    with (
        patch("veraxi_ymmp.pipeline.YMMPCompiler") as mock_compiler_cls,
        patch(
            "veraxi_ymmp.pipeline.validate_ymmp_timeline",
            return_value={"status": "PASS", "voice_items": 1},
        ) as mock_validate,
        patch(
            "veraxi_ymmp.pipeline.generate_project_thumbnail",
            return_value=fake_thumb,
        ) as mock_thumb,
    ):
        compiler_inst = MagicMock()
        compiler_inst.build_ir.return_value = (dummy_ir, [])
        mock_compiler_cls.return_value = compiler_inst

        pipeline = ProjectPipeline(
            use_tts=False,
            exporters={
                "premiere": mock_premiere_exp,
                "ymmp": mock_ymmp_exp,
                "qa": mock_qa_exp,
            },
        )
        result = pipeline.run(
            project_path=proj_dir,
            do_premiere=True,
            do_ymmp=True,
            do_qa=True,
            qa_duration=15.0,
            do_thumbnail=True,
        )

        assert result.success is True
        assert result.errors == []
        assert result.timeline_ir is dummy_ir
        assert result.premiere_xml == fake_xml
        assert result.ymmp_path == proj_dir / "ymmp" / "final_video.ymmp"
        assert result.ymmp_validation == {"status": "PASS", "voice_items": 1}
        assert result.qa_video_path == proj_dir / "qa_test.mp4"
        assert result.thumbnail_path == fake_thumb
        assert mock_premiere_exp.export.called
        assert mock_ymmp_exp.export.called
        assert mock_validate.called
        assert mock_qa_exp.export.called
        assert mock_thumb.called


def test_run_project_convenience_wrapper(tmp_path: Path) -> None:
    """run_project delegates to ProjectPipeline.run."""
    missing_dir = tmp_path / "does_not_exist"
    res = run_project(missing_dir, do_premiere=False, do_ymmp=False, do_qa=False, do_thumbnail=False)
    assert res.success is False
    assert len(res.errors) == 1


def test_normalize_all_platforms(tmp_path: Path) -> None:
    """normalize_all_platforms normalizes input video across all configured platforms."""
    src_video = tmp_path / "source.mp4"
    src_video.write_bytes(b"dummy_mp4_bytes")
    out_dir = tmp_path / "normalized"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        outputs = normalize_all_platforms(src_video, output_dir=out_dir)

        assert set(outputs.keys()) == set(PLATFORM_TARGETS.keys())
        assert mock_run.call_count == len(PLATFORM_TARGETS)
        for plat, out_path in outputs.items():
            assert out_path == (out_dir / f"source_{plat}.mp4").resolve()

def test_pipeline_progress_callback(tmp_path: Path) -> None:
    from veraxi_ymmp.pipeline import ProjectPipeline
    import json

    stages = []

    def cb(stage: str, ratio: float, msg: str) -> None:
        stages.append(stage)

    pipeline = ProjectPipeline(use_tts=False, progress_callback=cb)

    proj = tmp_path / "testproj"
    proj.mkdir()

    with open(proj / "script.json", "w", encoding="utf-8") as f:
        json.dump([{"character": "ずんだもん", "text": "テスト"}], f)

    pipeline.run(proj)

    assert "synthesizing_audio" in stages
    assert "exporting_ymmp_and_xml" in stages
