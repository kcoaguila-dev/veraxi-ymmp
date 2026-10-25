import pytest
from unittest.mock import patch

from veraxi_ymmp.api_server import APIHandler
from http.server import HTTPServer
import threading
import requests
import time
import socket

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="module")
def api_server():
    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), APIHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.1) # Wait for server to start
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join()

def test_api_projects_list(api_server, tmp_path):
    with patch("veraxi_ymmp.api_server.workspace_path", return_value=tmp_path):
        with patch("veraxi_ymmp.api_server.list_projects") as mock_list:
            mock_list.return_value = {"projects": [{"name": "test"}]}
            res = requests.get(f"{api_server}/api/projects")
            assert res.status_code == 200
            assert res.json() == {"projects": [{"name": "test"}]}

def test_api_project_create_traversal_rejection(api_server):
    res = requests.post(f"{api_server}/api/projects", json={"name": "../bad"})
    assert res.status_code == 400
    assert "Invalid project name" in res.json()["error"]

def test_api_script_saving(api_server, tmp_path):
    with patch("veraxi_ymmp.api_server.save_project_script") as mock_save:
        mock_save.return_value = {"success": True}
        res = requests.put(f"{api_server}/api/projects/myproj/script", json={
            "script": [{"character": "test", "text": "hello"}]
        })
        assert res.status_code == 200
        assert res.json() == {"success": True}

def test_api_script_saving_validation_error(api_server, tmp_path):
    with patch("veraxi_ymmp.api_server.save_project_script") as mock_save:
        mock_save.return_value = {
            "success": False,
            "valid": False,
            "errors": ["Bad emotion"],
            "reprompt_block": "REPROMPT"
        }
        res = requests.put(f"{api_server}/api/projects/myproj/script", json={
            "script": [{"character": "test", "text": "hello", "emotion": "invalid"}]
        })
        assert res.status_code == 422
        assert res.json()["reprompt_block"] == "REPROMPT"

def test_api_script_splitting(api_server):
    script = [{"character": "A", "text": "こんにちはなのだ！今日はすごくいい天気ですね。一緒にお散歩に行きましょう。"}]
    res = requests.post(f"{api_server}/api/projects/myproj/script/split", json={
        "script": script,
        "max_chars": 20
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["script"]) > 1

def test_api_serve_media_traversal(api_server, tmp_path):
    with patch("veraxi_ymmp.api_server.workspace_path") as mock_wp:
        mock_wp.return_value = tmp_path
        # Try to escape workspace
        res = requests.get(f"{api_server}/api/projects/test/media/..%2F..%2Fetc%2Fpasswd")
        assert res.status_code == 403

def test_api_ai_prompt(api_server):
    with patch("veraxi_ymmp.api_server.get_ai_prompt_spec") as mock_prompt:
        mock_prompt.return_value = {"prompt_markdown": "Test"}
        res = requests.get(f"{api_server}/api/ai-prompt")
        assert res.status_code == 200
        assert res.json()["prompt_markdown"] == "Test"

def test_api_youtube_schedule_validation(api_server):
    with patch("veraxi_ymmp.api_server.upload_project_to_youtube") as mock_up:
        mock_up.side_effect = ValueError("Scheduling requires private")
        res = requests.post(f"{api_server}/api/projects/test/youtube", json={
            "title": "T",
            "privacy_status": "public",
            "publish_at": "2030-01-01T00:00:00Z"
        })
        assert res.status_code == 500
        assert "Scheduling requires private" in res.json()["error"]

def test_api_integration_lifecycle(api_server, tmp_path):
    # Unmocked test wrapping workspace_path correctly
    def mock_wp(p):
        return tmp_path / p

    def mock_cwd():
        return tmp_path

    with patch("veraxi_ymmp.api_server.workspace_path", side_effect=mock_wp),          patch("veraxi_ymmp.mcp_server.workspace_path", side_effect=mock_wp),          patch("pathlib.Path.cwd", side_effect=mock_cwd):

        # 1. Create project
        res_create = requests.post(f"{api_server}/api/projects", json={"name": "integration_test"})
        assert res_create.status_code == 200
        assert res_create.json()["success"] is True

        # 2. List projects to verify it was created
        res_list = requests.get(f"{api_server}/api/projects")
        assert res_list.status_code == 200
        projects = res_list.json()["projects"]
        assert any(p["name"] == "integration_test" for p in projects)

        # 3. Save a script to the project
        valid_script = [{"character": "ずんだもん", "text": "こんにちは", "emotion": "normal", "motion": "none", "character_position": "center", "subtitle_position": "bottom_center", "subtitle_style": "outlined", "bgm": None, "sfx": None, "image": None}]
        res_save = requests.put(f"{api_server}/api/projects/integration_test/script", json={
            "script": valid_script
        })
        assert res_save.status_code == 200
        assert res_save.json()["success"] is True

        # 4. Load the project and verify the script persisted correctly
        res_load = requests.get(f"{api_server}/api/projects/integration_test")
        assert res_load.status_code == 200
        data = res_load.json()
        assert data.get("script") == valid_script
