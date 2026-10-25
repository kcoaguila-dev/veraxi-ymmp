import json
import socket
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from veraxi_ymmp.api_server import APIHandler
from veraxi_ymmp.pipeline import PipelineResult


def get_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port = int(s.getsockname()[1])
    s.close()
    return port


@pytest.fixture(scope="module")
def api_server():
    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), APIHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.1)  # Wait for server to start
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_api_projects_list(api_server: str, tmp_path: Path) -> None:
    with patch("veraxi_ymmp.api_server.workspace_path", return_value=tmp_path):
        with patch("veraxi_ymmp.api_server.list_projects") as mock_list:
            mock_list.return_value = {"projects": [{"name": "test"}]}
            res = requests.get(f"{api_server}/api/projects")
            assert res.status_code == 200
            assert res.json() == {"projects": [{"name": "test"}]}


def test_api_project_create_traversal_rejection(api_server: str) -> None:
    res = requests.post(f"{api_server}/api/projects", json={"name": "../bad"})
    assert res.status_code == 400
    assert "Invalid project name" in res.json()["error"]


def test_api_script_saving(api_server: str, tmp_path: Path) -> None:
    with patch("veraxi_ymmp.api_server.save_project_script") as mock_save:
        mock_save.return_value = {"success": True}
        res = requests.put(
            f"{api_server}/api/projects/myproj/script",
            json={"script": [{"character": "test", "text": "hello"}]},
        )
        assert res.status_code == 200
        assert res.json() == {"success": True}
        mock_save.assert_called_once_with(
            "projects/myproj",
            '[{"character": "test", "text": "hello"}]',
            None,
        )


def test_api_script_saving_validation_error(api_server: str, tmp_path: Path) -> None:
    with patch("veraxi_ymmp.api_server.save_project_script") as mock_save:
        mock_save.return_value = {
            "success": False,
            "valid": False,
            "errors": ["Bad emotion"],
            "reprompt_block": "REPROMPT",
        }
        res = requests.put(
            f"{api_server}/api/projects/myproj/script",
            json={"script": [{"character": "test", "text": "hello", "emotion": "invalid"}]},
        )
        assert res.status_code == 422
        assert res.json()["reprompt_block"] == "REPROMPT"


def test_api_script_splitting(api_server: str) -> None:
    script = [
        {
            "character": "A",
            "text": "こんにちはなのだ！今日はすごくいい天気ですね。一緒にお散歩に行きましょう。",
        }
    ]
    res = requests.post(
        f"{api_server}/api/projects/myproj/script/split",
        json={"script": script, "max_chars": 20},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["script"]) > 1


def test_api_serve_media_traversal(api_server: str, tmp_path: Path) -> None:
    with patch("veraxi_ymmp.api_server.workspace_path") as mock_wp:
        mock_wp.return_value = tmp_path
        res = requests.get(f"{api_server}/api/projects/test/media/..%2F..%2Fetc%2Fpasswd")
        assert res.status_code == 403


def test_api_ai_prompt(api_server: str) -> None:
    with patch("veraxi_ymmp.api_server.get_ai_prompt_spec") as mock_prompt:
        mock_prompt.return_value = {"prompt_markdown": "Test"}
        res = requests.get(f"{api_server}/api/ai-prompt")
        assert res.status_code == 200
        assert res.json()["prompt_markdown"] == "Test"


def test_api_youtube_schedule_validation(api_server: str) -> None:
    with patch("veraxi_ymmp.api_server.upload_project_to_youtube") as mock_up:
        mock_up.side_effect = ValueError("Scheduling requires private")
        res = requests.post(
            f"{api_server}/api/projects/test/youtube",
            json={
                "title": "T",
                "privacy_status": "public",
                "publish_at": "2030-01-01T00:00:00Z",
            },
        )
        assert res.status_code == 500
        assert "Scheduling requires private" in res.json()["error"]


def test_api_pipeline_run_and_status_path_serialization(
    api_server: str, tmp_path: Path
) -> None:
    fake_res = PipelineResult(
        project_dir=tmp_path / "projects" / "demo",
        ymmp_path=tmp_path / "projects" / "demo" / "ymmp" / "final_video.ymmp",
        qa_video_path=tmp_path / "projects" / "demo" / "qa_test.mp4",
        thumbnail_path=tmp_path / "projects" / "demo" / "thumbnail.png",
        success=True,
    )
    with (
        patch("veraxi_ymmp.api_server.workspace_path", return_value=tmp_path / "projects" / "demo"),
        patch("veraxi_ymmp.pipeline.ProjectPipeline.run", return_value=fake_res),
    ):
        res_run = requests.post(f"{api_server}/api/projects/demo/run", json={"use_tts": False})
        assert res_run.status_code == 200
        time.sleep(0.1)
        res_status = requests.get(f"{api_server}/api/projects/demo/status")
        assert res_status.status_code == 200
        status_data = res_status.json()
        assert status_data["status"] == "complete"
        assert status_data["result"]["success"] is True
        assert status_data["result"]["qa_video_path"].endswith("qa_test.mp4")


def test_api_integration_lifecycle(api_server: str, tmp_path: Path) -> None:
    def mock_wp(p: str) -> Path:
        return tmp_path / p

    def mock_cwd() -> Path:
        return tmp_path

    with (
        patch("veraxi_ymmp.api_server.workspace_path", side_effect=mock_wp),
        patch("veraxi_ymmp.mcp_server.workspace_path", side_effect=mock_wp),
        patch("pathlib.Path.cwd", side_effect=mock_cwd),
    ):
        # 1. Create project
        res_create = requests.post(
            f"{api_server}/api/projects", json={"name": "integration_test"}
        )
        assert res_create.status_code == 200
        assert res_create.json()["success"] is True

        # 2. List projects to verify it was created
        res_list = requests.get(f"{api_server}/api/projects")
        assert res_list.status_code == 200
        projects = res_list.json()["projects"]
        assert any(p["name"] == "integration_test" for p in projects)

        # 3. Save a script to the project
        valid_script = [
            {
                "character": "ずんだもん",
                "text": "こんにちは",
                "emotion": "normal",
                "motion": "none",
                "character_position": "center",
                "subtitle_position": "bottom_center",
                "subtitle_style": "outlined",
                "bgm": None,
                "sfx": None,
                "image": None,
            }
        ]
        res_save = requests.put(
            f"{api_server}/api/projects/integration_test/script",
            json={"script": valid_script},
        )
        assert res_save.status_code == 200
        assert res_save.json()["success"] is True

        # 4. Load the project and verify the script persisted correctly
        res_load = requests.get(f"{api_server}/api/projects/integration_test")
        assert res_load.status_code == 200
        data = res_load.json()
        assert data.get("script") == valid_script


def test_api_voicevox_audition_success(api_server: str, tmp_path: Path) -> None:
    fake_wav = tmp_path / "test_audition.wav"
    fake_wav.write_bytes(b"RIFFdummywavdata")

    with patch("veraxi_ymmp.api_server.audition_voice") as mock_audition:
        mock_audition.return_value = {
            "path": str(fake_wav),
            "duration_seconds": 1.5,
        }
        res = requests.post(
            f"{api_server}/api/voicevox/audition",
            json={"text": "こんにちは", "character": "ずんだもん", "speed": 1.0},
        )
        assert res.status_code == 200
        assert res.headers["Content-Type"] == "audio/wav"
        assert res.content == b"RIFFdummywavdata"
        # Verify the temporary file was cleaned up (allow server thread a moment to unlink)
        for _ in range(20):
            if not fake_wav.exists():
                break
            time.sleep(0.05)
        assert not fake_wav.exists()


def test_api_voicevox_audition_error(api_server: str) -> None:
    with patch("veraxi_ymmp.api_server.audition_voice") as mock_audition:
        mock_audition.side_effect = RuntimeError("Voicevox offline")
        res = requests.post(
            f"{api_server}/api/voicevox/audition",
            json={"text": "こんにちは", "character": "ずんだもん"},
        )
        assert res.status_code == 500
        assert "Voicevox offline" in res.json()["error"]


def test_api_history_lifecycle(api_server: str, tmp_path: Path) -> None:
    with patch("veraxi_ymmp.api_server.workspace_path", return_value=tmp_path / "projects" / "hist_proj"):
        proj_dir = tmp_path / "projects" / "hist_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "script.json").write_text(
            json.dumps([{"character": "ずんだもん", "text": "初期バージョンなのだ！"}]),
            encoding="utf-8"
        )

        from veraxi_ymmp.history import backup_project_script
        snap_id = backup_project_script(proj_dir, reason="api_test")
        assert snap_id is not None

        # 1. GET /api/projects/hist_proj/history
        res = requests.get(f"{api_server}/api/projects/hist_proj/history")
        assert res.status_code == 200
        history = res.json().get("history", [])
        assert len(history) == 1
        assert history[0]["id"] == snap_id

        # 2. Overwrite script
        (proj_dir / "script.json").write_text(
            json.dumps([{"character": "四国めたん", "text": "変更後ですわ。"}]),
            encoding="utf-8"
        )

        # 3. POST /api/projects/hist_proj/history/restore
        res_restore = requests.post(
            f"{api_server}/api/projects/hist_proj/history/restore",
            json={"history_id": snap_id}
        )
        assert res_restore.status_code == 200
        assert res_restore.json()["success"] is True

        # Verify disk script is restored
        restored_data = json.loads((proj_dir / "script.json").read_text(encoding="utf-8"))
        assert restored_data[0]["text"] == "初期バージョンなのだ！"
