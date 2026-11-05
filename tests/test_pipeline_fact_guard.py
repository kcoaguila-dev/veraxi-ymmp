"""Fail-closed fact-check and local quote verification tests for ProjectPipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from veraxi_ymmp.ir import TimelineIR, VoiceClip
from veraxi_ymmp.pipeline import ProjectPipeline
from veraxi_ymmp.ports import ExportResult


def _create_minimal_project(proj_dir: Path) -> Path:
    proj_dir.mkdir(parents=True, exist_ok=True)
    script = [{"character": "ずんだもん", "text": "テストなのだ"}]
    (proj_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    return proj_dir


def test_pipeline_blocks_when_claims_json_missing(tmp_path: Path) -> None:
    proj_dir = _create_minimal_project(tmp_path / "proj_no_claims")
    pipeline = ProjectPipeline(use_tts=False)

    result = pipeline.run(
        proj_dir,
        do_premiere=False,
        do_ymmp=False,
        do_qa=False,
        do_thumbnail=False,
        allow_unverified=False,
    )

    assert result.success is False
    assert any("No claim ledger found" in err for err in result.errors)
    assert any("allow_unverified=True" in err for err in result.errors)


def test_pipeline_bypasses_gate_when_allow_unverified_enabled(tmp_path: Path) -> None:
    proj_dir = _create_minimal_project(tmp_path / "proj_unverified_allowed")
    fake_thumb = proj_dir / "thumbnail.png"
    fake_thumb.write_bytes(b"\x00" * 100)

    dummy_ir = TimelineIR(
        fps=60,
        total_frames=60,
        voice_clips=[
            VoiceClip(
                start_frame=0,
                length=60,
                character="ずんだもん",
                text="テストなのだ",
                emotion="normal",
                motion="none",
                audio_path=None,
                hatsuon="テストナノダ",
                subtitle_position="bottom_center",
                subtitle_style="outlined",
            )
        ],
    )

    mock_exp = MagicMock()
    mock_exp.export.return_value = ExportResult(target_format="ymmp", output_path=proj_dir / "out.ymmp")

    with (
        patch("veraxi_ymmp.pipeline.YMMPCompiler") as mock_compiler,
        patch("veraxi_ymmp.pipeline.validate_ymmp_timeline", return_value={"status": "PASS"}),
        patch("veraxi_ymmp.pipeline.generate_project_thumbnail", return_value=fake_thumb),
    ):
        inst = MagicMock()
        inst.build_ir.return_value = (dummy_ir, [])
        mock_compiler.return_value = inst

        pipeline = ProjectPipeline(use_tts=False, exporters={"ymmp": mock_exp})
        result = pipeline.run(
            proj_dir,
            do_premiere=False,
            do_ymmp=True,
            do_qa=False,
            do_thumbnail=False,
            allow_unverified=True,
        )

        assert result.success is True
        assert not any("No claim ledger found" in err for err in result.errors)


def test_pipeline_blocks_when_central_claim_unverified(tmp_path: Path) -> None:
    proj_dir = _create_minimal_project(tmp_path / "proj_central_unverified")
    claims = [{"id": "c1", "cut_index": 0, "text": "売上は100億ドル", "kind": "number", "weight": "central", "evidence": []}]
    (proj_dir / "claims.json").write_text(json.dumps(claims, ensure_ascii=False), encoding="utf-8")

    pipeline = ProjectPipeline(use_tts=False)
    result = pipeline.run(
        proj_dir,
        do_premiere=False,
        do_ymmp=False,
        do_qa=False,
        do_thumbnail=False,
        allow_unverified=False,
    )

    assert result.success is False
    assert any("[FACTS] c1" in err for err in result.errors)
    assert any("central claim needs 2 primary sources" in err for err in result.errors)



def test_pipeline_blocks_when_stored_quote_is_hallucinated(tmp_path: Path) -> None:
    proj_dir = _create_minimal_project(tmp_path / "proj_quote_hallucinated")
    sources_dir = proj_dir / "sources"
    sources_dir.mkdir()
    (sources_dir / "sec_report.txt").write_text("Revenue was $50B in FY2026.", encoding="utf-8")

    claims = [{
        "id": "c1",
        "cut_index": 0,
        "text": "Revenue was $99B",
        "kind": "number",
        "weight": "minor",
        "evidence": [{
            "url": "https://sec.gov/doc",
            "quote": "Revenue was $99B",  # Hallucinated quote
            "stance": "confirms",
            "tier": 1,
            "source_id": "sec_report",
        }],
    }]
    (proj_dir / "claims.json").write_text(json.dumps(claims, ensure_ascii=False), encoding="utf-8")

    pipeline = ProjectPipeline(use_tts=False)
    result = pipeline.run(
        proj_dir,
        do_premiere=False,
        do_ymmp=False,
        do_qa=False,
        do_thumbnail=False,
        allow_unverified=False,
    )

    assert result.success is False
    assert any("quote not found in stored source 'sec_report'" in err for err in result.errors)


def test_pipeline_succeeds_when_claims_verified_against_stored_source(tmp_path: Path) -> None:
    proj_dir = _create_minimal_project(tmp_path / "proj_verified_ok")
    fake_thumb = proj_dir / "thumbnail.png"
    fake_thumb.write_bytes(b"\x00" * 100)

    sources_dir = proj_dir / "sources"
    sources_dir.mkdir()
    (sources_dir / "sec_report.txt").write_text("Revenue was $50B in FY2026.", encoding="utf-8")

    claims = [{
        "id": "c1",
        "cut_index": 0,
        "text": "Revenue was $50B",
        "kind": "number",
        "weight": "minor",
        "evidence": [{
            "url": "https://sec.gov/doc",
            "quote": "Revenue was $50B",
            "stance": "confirms",
            "tier": 1,
            "source_id": "sec_report",
        }],
    }]
    (proj_dir / "claims.json").write_text(json.dumps(claims, ensure_ascii=False), encoding="utf-8")

    dummy_ir = TimelineIR(
        fps=60,
        total_frames=60,
        voice_clips=[
            VoiceClip(
                start_frame=0,
                length=60,
                character="ずんだもん",
                text="テストなのだ",
                emotion="normal",
                motion="none",
                audio_path=None,
                hatsuon="テストナノダ",
                subtitle_position="bottom_center",
                subtitle_style="outlined",
            )
        ],
    )

    mock_exp = MagicMock()
    mock_exp.export.return_value = ExportResult(target_format="ymmp", output_path=proj_dir / "out.ymmp")

    with (
        patch("veraxi_ymmp.pipeline.YMMPCompiler") as mock_compiler,
        patch("veraxi_ymmp.pipeline.validate_ymmp_timeline", return_value={"status": "PASS"}),
        patch("veraxi_ymmp.pipeline.generate_project_thumbnail", return_value=fake_thumb),
    ):
        inst = MagicMock()
        inst.build_ir.return_value = (dummy_ir, [])
        mock_compiler.return_value = inst

        pipeline = ProjectPipeline(use_tts=False, exporters={"ymmp": mock_exp})
        result = pipeline.run(
            proj_dir,
            do_premiere=False,
            do_ymmp=True,
            do_qa=False,
            do_thumbnail=False,
            allow_unverified=False,
        )

        assert result.success is True
        assert result.fact_audit_outcome is not None
        assert not result.fact_audit_outcome.blocked
        assert (proj_dir / "sources.md").is_file()
