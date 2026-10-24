"""Unit tests for veraxi_ymmp.mcp_server tools and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
pytest.importorskip("mcp")


from veraxi_ymmp.mcp_server import (
    list_projects,
    load_project,
    save_project_script,
    upload_project_to_youtube
)
from veraxi_ymmp.mcp_server import (
    compile_project,
    generate_thumbnail_tool,
    inspect_template,
    parse_json,
    run_pipeline,
    validate_script,
    workspace_path,
    get_voicevox_health,
    audition_voice,
    render_broll_slides,
    normalize_project_audio,
    launch_ymm4_desktop
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

@patch("veraxi_ymmp.mcp_server.VoicevoxClient.is_available", return_value=True)
@patch("veraxi_ymmp.mcp_server.VoicevoxClient.get_speakers", return_value=[{"name": "ずんだもん"}])
def test_get_voicevox_health(mock_speakers, mock_is_available) -> None:
    res = get_voicevox_health("http://fake")
    assert res["available"] is True
    assert res["url"] == "http://fake"
    assert res["speakers"] == [{"name": "ずんだもん"}]

@patch("veraxi_ymmp.mcp_server.VoicevoxClient.get_audio_query")
@patch("requests.post")
def test_audition_voice(mock_post, mock_get_audio_query) -> None:
    mock_get_audio_query.return_value = {"accent_phrases": [{"moras": [1, 2]}]}
    import io
    import wave

    # Create a valid dummy wav file in memory
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000) # 1 second of silence
    mock_post.return_value.content = buf.getvalue()
    mock_post.return_value.raise_for_status = lambda: None

    res = audition_voice("テスト", 3)
    assert Path(res["path"]).exists()
    assert res["duration_seconds"] == 1.0

@patch("veraxi_ymmp.mcp_server.render_from_manifest")
@patch("veraxi_ymmp.mcp_server.Image.open")
def test_render_broll_slides(mock_image_open, mock_render) -> None:
    mock_render.return_value = [Path("fake1.png"), Path("fake2.png")]
    mock_img = mock_image_open.return_value.__enter__.return_value
    mock_img.size = (1920, 1080)

    res = render_broll_slides("manifest.json")
    assert len(res["slides"]) == 2
    assert res["slides"][0]["width"] == 1920

@patch("subprocess.run")
@patch("veraxi_ymmp.mcp_server.normalize_video_audio")
def test_normalize_project_audio(mock_normalize, mock_run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    proj = tmp_path / "testproj"
    proj.mkdir()
    (proj / "final_video.mp4").touch()

    mock_run.return_value.stderr = '{"input_i": "-10.0", "input_tp": "-0.5"}'
    mock_normalize.return_value = proj / "final_video_youtube.mp4"

    res = normalize_project_audio("testproj")
    assert res["measured_i"] == -10.0
    assert res["measured_tp"] == -0.5
    assert res["target_lufs"] == -14.0
    assert "youtube" in res["output_path"]

@patch("subprocess.Popen")
def test_launch_ymm4_desktop(mock_popen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YMM4_PATH", "fake_path.exe")
    monkeypatch.setattr("os.path.exists", lambda p: True)

    proj = tmp_path / "testproj"
    proj.mkdir()
    (proj / "test.ymmp").touch()

    res = launch_ymm4_desktop("testproj")
    assert res["launched"] is True
    assert res["executable"] == "fake_path.exe"



def test_list_projects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    proj_dir = tmp_path / "projects" / "testproj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "script.json").touch()

    res = list_projects()
    assert len(res["projects"]) == 1
    assert res["projects"][0]["name"] == "testproj"
    assert res["projects"][0]["has_script"] is True
    assert res["projects"][0]["has_broll_manifest"] is False

def test_load_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    proj_dir = tmp_path / "projects" / "testproj"
    proj_dir.mkdir(parents=True)

    script_data = [{"character": "zundamon", "text": "hello"}]
    (proj_dir / "script.json").write_text(json.dumps(script_data))
    (proj_dir / "qa_test.mp4").touch()

    res = load_project("projects/testproj")
    assert res["script"] == script_data
    assert res["qa_video_path"] is not None
    assert res["thumbnail_path"] is None

def test_save_project_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    proj_dir = tmp_path / "projects" / "testproj"
    proj_dir.mkdir(parents=True)

    script_data = [{"character": "zundamon", "text": "a" * 40}] # > 35 chars
    res = save_project_script("projects/testproj", json.dumps(script_data))

    assert res["success"] is True
    assert len(res["warnings"]) == 1
    assert (proj_dir / "script.json").exists()

@patch("veraxi_ymmp.youtube_adapter.MockYouTubeAdapter.upload_video")
@patch("veraxi_ymmp.youtube_adapter.MockYouTubeAdapter.upload_caption")
def test_upload_project_to_youtube(mock_upload_caption, mock_upload_video, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    proj_dir = tmp_path / "projects" / "testproj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "qa_test.mp4").touch()
    (proj_dir / "test.srt").touch()

    from veraxi_ymmp.ir import UploadResult
    mock_upload_video.return_value = UploadResult(video_id="fakeid", status="uploaded", thumbnail_uploaded=False, bytes_uploaded=100, url="http://fakeurl")

    res = upload_project_to_youtube(
        project_dir="projects/testproj",
        title="test",
        mock_upload=True
    )

    assert res["success"] is True
    assert res["video_id"] == "fakeid"
    assert res["caption_uploaded"] is True
