"""Unit tests for veraxi_ymmp.mcp_server tools and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from veraxi_ymmp.mcp_server import (
    compile_project,
    generate_thumbnail_tool,
    inspect_template,
    parse_json,
    run_pipeline,
    validate_script,
    workspace_path,
)
from veraxi_ymmp.pipeline import PipelineResult


def test_workspace_path_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """workspace_path resolves relative paths inside the workspace root."""
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "projects" / "demo"
    sub.mkdir(parents=True)

    resolved = workspace_path("projects/demo")
    assert resolved == sub.resolve()


def test_workspace_path_traversal_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """workspace_path blocks directory traversal outside workspace root."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    with pytest.raises(ValueError, match="Path must stay inside the workspace"):
        workspace_path("../outside.json")


def test_parse_json_valid_and_invalid() -> None:
    """parse_json parses valid JSON and raises ValueError on malformed JSON."""
    assert parse_json('[{"character": "ずんだもん", "text": "テスト"}]', "script") == [
        {"character": "ずんだもん", "text": "テスト"}
    ]

    with pytest.raises(ValueError, match="Invalid script JSON"):
        parse_json("{not valid json", "script")


def test_inspect_template() -> None:
    """inspect_template returns structural metadata about a template file."""
    info = inspect_template("tests/fixtures/sample_template.ymmp")
    assert info["timeline_layout"] in ("Timeline", "Timelines")
    assert "ゆっくり霊夢" in info["characters"]
    assert info["item_count"] > 0
    assert info["has_voice_template"] is True


def test_validate_script_writer_and_director() -> None:
    """validate_script distinguishes Writer and Director JSON scripts and validates parity."""
    writer_raw = json.dumps(
        [{"character": "ゆっくり霊夢", "text": "こんにちは"}],
        ensure_ascii=False,
    )
    res_writer = validate_script(writer_raw)
    assert res_writer["valid"] is True
    assert res_writer["type"] == "writer"

    director_raw = json.dumps(
        [
            {
                "character": "ゆっくり霊夢",
                "text": "こんにちは",
                "emotion": "happy",
                "motion": "none",
                "bgm": None,
                "sfx": None,
                "image": None,
            }
        ],
        ensure_ascii=False,
    )
    res_director = validate_script(director_raw, writer_json=writer_raw)
    assert res_director["valid"] is True
    assert res_director["type"] == "director"


def test_compile_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """compile_project compiles a script into an output .ymmp inside the workspace."""
    repo_root = Path(__file__).resolve().parent.parent
    template_src = repo_root / "tests" / "fixtures" / "sample_template.ymmp"

    monkeypatch.chdir(tmp_path)
    local_template = tmp_path / "sample_template.ymmp"
    local_template.write_bytes(template_src.read_bytes())

    script_json = json.dumps(
        [{"character": "ゆっくり霊夢", "text": "MCPコンパイルテスト"}],
        ensure_ascii=False,
    )
    res = compile_project(
        template="sample_template.ymmp",
        script_json=script_json,
        output="compiled_out.ymmp",
        tts=False,
    )
    assert Path(res["output"]).exists()
    assert res["voice_items"] == 1
    assert res["total_frames"] > 0


def test_run_pipeline_and_generate_thumbnail_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """run_pipeline and generate_thumbnail_tool delegate to pipeline and thumbnail services."""
    monkeypatch.chdir(tmp_path)
    proj_dir = tmp_path / "demo_proj"
    proj_dir.mkdir()

    fake_result = PipelineResult(
        project_dir=proj_dir,
        ymmp_path=proj_dir / "ymmp" / "final_video.ymmp",
        premiere_xml=proj_dir / "premiere" / "demo_proj.xml",
        qa_video_path=proj_dir / "qa_test.mp4",
        thumbnail_path=proj_dir / "thumbnail.png",
        success=True,
    )
    with patch("veraxi_ymmp.mcp_server.ProjectPipeline.run", return_value=fake_result):
        raw = run_pipeline("demo_proj", use_tts=False)
        parsed = json.loads(raw)
        assert parsed["success"] is True
        assert parsed["project_dir"] == str(proj_dir)

    expected_thumb = proj_dir / "thumbnail.png"
    with patch(
        "veraxi_ymmp.mcp_server.generate_project_thumbnail",
        return_value=expected_thumb,
    ) as mock_thumb:
        thumb_res = generate_thumbnail_tool("demo_proj")
        assert thumb_res == str(expected_thumb)
        assert mock_thumb.called
