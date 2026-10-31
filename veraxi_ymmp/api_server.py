import http.server
import json
import re
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict

from veraxi_ymmp.logging import logger
from veraxi_ymmp.mcp_server import (
    list_projects,
    load_project,
    save_project_script,
    get_voicevox_health,
    audition_voice,
    launch_ymm4_desktop,
    upload_project_to_youtube,
    get_ai_prompt_spec,
    normalize_project_audio,
    generate_thumbnail_tool,
    workspace_path,
)
from veraxi_ymmp.script import split_long_script_entries

# Global state for pipeline status
_pipeline_status: Dict[str, Any] = {}
_pipeline_lock = threading.Lock()


def _project_rel_path(project_name: str) -> str:
    if ".." in project_name or "/" in project_name or "\\" in project_name:
        raise ValueError("Invalid project name")
    return f"projects/{project_name}"


class APIHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:1420')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def send_json(self, status_code: int, data: Any) -> None:
        try:
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        except TypeError as e:
            logger.error(f"JSON serialization error: {e}, data: {data}")
            self.send_error(500, "Internal Server Error")
            return
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:1420')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path

            if path == '/api/projects':
                return self.send_json(200, list_projects())

            if path == '/api/ai-prompt':
                return self.send_json(200, get_ai_prompt_spec())

            if path == '/api/voicevox/health':
                return self.send_json(200, get_voicevox_health())

            if path == '/api/youtube/auth/status':
                from veraxi_ymmp.youtube_auth import get_auth_status
                status = get_auth_status()
                query = urllib.parse.parse_qs(parsed_path.query)
                if query.get("include_channel", ["0"])[0] in ("1", "true") and status.get("authenticated"):
                    try:
                        from veraxi_ymmp.youtube_adapter import YouTubeAdapter
                        adapter = YouTubeAdapter()
                        status["channel"] = adapter.get_channel_info()
                    except Exception as ex:
                        logger.debug(f"Could not fetch channel info: {ex}")
                return self.send_json(200, status)

            match = re.match(r'^/api/projects/([^/]+)$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                return self.send_json(200, load_project(_project_rel_path(project_name)))

            match = re.match(r'^/api/projects/([^/]+)/history$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                from veraxi_ymmp.history import list_script_history
                proj_path = workspace_path(_project_rel_path(project_name))
                history = list_script_history(proj_path)
                return self.send_json(200, {"history": history})

            match = re.match(r'^/api/projects/([^/]+)/status$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                with _pipeline_lock:
                    status = _pipeline_status.get(project_name, {"status": "idle"})
                return self.send_json(200, status)

            match = re.match(r'^/api/projects/([^/]+)/media/(.+)$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                filename = urllib.parse.unquote(match.group(2))
                return self.serve_media_file(project_name, filename)

            self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"GET error: {e}", exc_info=True)
            self.send_json(500, {"error": str(e)})

    def serve_media_file(self, project_name: str, filename: str) -> None:
        try:
            proj_dir = workspace_path(_project_rel_path(project_name))
            file_path = (proj_dir / filename).resolve()

            if not str(file_path).startswith(str(proj_dir.resolve())):
                self.send_error(403, "Forbidden")
                return

            if (not file_path.exists() or not file_path.is_file()) and filename.startswith("assets/"):
                ws_root = workspace_path(".").resolve()
                ws_candidate = (ws_root / filename).resolve()
                if str(ws_candidate).startswith(str(ws_root)) and ws_candidate.exists() and ws_candidate.is_file():
                    file_path = ws_candidate

            if not file_path.exists() or not file_path.is_file():
                self.send_error(404, "Not Found")
                return

            content_type = self.guess_type(str(file_path))

            # Simple Range support for video
            stat = file_path.stat()
            file_size = stat.st_size

            range_header = self.headers.get('Range')
            if range_header and content_type.startswith('video/'):
                match = re.match(r'bytes=(\d+)-(\d*)', range_header)
                if match:
                    start = int(match.group(1))
                    end_str = match.group(2)
                    end = int(end_str) if end_str else file_size - 1

                    if start >= file_size or end >= file_size:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{file_size}')
                        self.end_headers()
                        return

                    length = end - start + 1
                    self.send_response(206)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Access-Control-Allow-Origin', 'http://localhost:1420')
                    self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                    self.send_header('Content-Length', str(length))
                    self.send_header('Accept-Ranges', 'bytes')
                    self.end_headers()

                    with open(file_path, 'rb') as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                    return

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Access-Control-Allow-Origin', 'http://localhost:1420')
            self.send_header('Content-Length', str(file_size))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())

        except (ConnectionResetError, BrokenPipeError):
            return
        except Exception as e:
            logger.error(f"Media error: {e}", exc_info=True)
            try:
                self.send_error(500, str(e))
            except (ConnectionResetError, BrokenPipeError):
                pass

    def do_POST(self) -> None:
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
            try:
                body = json.loads(post_data)
            except json.JSONDecodeError:
                body = {}

            if path == '/api/projects':
                name = body.get("name", "Untitled")
                # Basic protection
                try:
                    proj_path = workspace_path(_project_rel_path(name))
                except ValueError:
                    return self.send_json(400, {"error": "Invalid project name"})
                proj_path.mkdir(parents=True, exist_ok=True)
                script_path = proj_path / "script.json"
                if not script_path.exists():
                    script_path.write_text("[]", encoding="utf-8")
                return self.send_json(200, {"success": True, "name": name})

            if path == '/api/voicevox/audition':
                text = body.get("text", "")
                character = body.get("character", "unknown")
                speed = body.get("speed", 1.0)
                from veraxi_ymmp.constants import DEFAULT_SPEAKER_MAP
                speaker_id = body.get("speaker_id", DEFAULT_SPEAKER_MAP.get(character, 3))

                try:
                    res = audition_voice(text, speaker_id, speed)
                    wav_path = Path(res["path"])
                    if wav_path.exists():
                        self.send_response(200)
                        self.send_header('Content-Type', 'audio/wav')
                        self.send_header('Access-Control-Allow-Origin', 'http://localhost:1420')
                        self.send_header('Content-Length', str(wav_path.stat().st_size))
                        self.end_headers()
                        with open(wav_path, 'rb') as f:
                            self.wfile.write(f.read())
                        try:
                            wav_path.unlink()
                        except OSError:
                            pass
                        return
                    else:
                        return self.send_json(500, {"error": "WAV file not found"})
                except Exception as e:
                    return self.send_json(500, {"error": str(e)})

            match = re.match(r'^/api/projects/([^/]+)/script/split$', path)
            if match:
                script = body.get("script", [])
                max_chars = body.get("max_chars", 40)
                split = split_long_script_entries(script, max_chars=max_chars)
                return self.send_json(200, {"script": split})

            match = re.match(r'^/api/projects/([^/]+)/run$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                use_tts = body.get("use_tts", True)

                with _pipeline_lock:
                    _pipeline_status[project_name] = {
                        "status": "running",
                        "stage": "starting",
                        "progress": 0.0,
                        "message": "",
                    }

                def run_bg() -> None:
                    def cb(stage: str, ratio: float, msg: str) -> None:
                        with _pipeline_lock:
                            _pipeline_status[project_name] = {
                                "status": "running",
                                "stage": stage,
                                "progress": ratio * 100,
                                "message": msg
                            }
                    try:
                        from veraxi_ymmp.pipeline import ProjectPipeline
                        import dataclasses
                        res_obj = ProjectPipeline(use_tts=use_tts, progress_callback=cb).run(
                            workspace_path(_project_rel_path(project_name))
                        )
                        res = dataclasses.asdict(res_obj)
                        with _pipeline_lock:
                            _pipeline_status[project_name] = {
                                "status": "complete",
                                "result": res
                            }
                    except Exception as e:
                        logger.error(f"Pipeline error: {e}", exc_info=True)
                        with _pipeline_lock:
                            _pipeline_status[project_name] = {
                                "status": "error",
                                "error": str(e)
                            }

                thread = threading.Thread(target=run_bg)
                thread.start()
                return self.send_json(200, {"success": True, "message": "Pipeline started"})

            match = re.match(r'^/api/projects/([^/]+)/ymm4$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                try:
                    return self.send_json(200, launch_ymm4_desktop(_project_rel_path(project_name)))
                except Exception as e:
                    return self.send_json(500, {"error": str(e)})

            match = re.match(r'^/api/projects/([^/]+)/normalize$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                try:
                    return self.send_json(200, normalize_project_audio(_project_rel_path(project_name)))
                except Exception as e:
                    return self.send_json(500, {"error": str(e)})

            match = re.match(r'^/api/projects/([^/]+)/thumbnail$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                try:
                    thumb_path = generate_thumbnail_tool(_project_rel_path(project_name))
                    return self.send_json(200, {"success": True, "thumbnail_path": thumb_path})
                except Exception as e:
                    return self.send_json(500, {"error": str(e)})

            match = re.match(r'^/api/projects/([^/]+)/history/restore$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                history_id = body.get("history_id", "")
                from veraxi_ymmp.history import restore_script_history
                try:
                    proj_path = workspace_path(_project_rel_path(project_name))
                    result = restore_script_history(proj_path, history_id)
                    return self.send_json(200, result)
                except (ValueError, FileNotFoundError) as e:
                    return self.send_json(400, {"error": str(e)})
                except Exception as e:
                    return self.send_json(500, {"error": str(e)})

            match = re.match(r'^/api/projects/([^/]+)/youtube$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                try:
                    return self.send_json(200, upload_project_to_youtube(
                        project_dir=_project_rel_path(project_name),
                        title=body.get("title", project_name),
                        privacy_status=body.get("privacy_status", "private"),
                        description=body.get("description", ""),
                        tags=body.get("tags"),
                        publish_at=body.get("publish_at"),
                        mock_upload=body.get("mock_upload", False)
                    ))
                except Exception as e:
                    return self.send_json(500, {"error": str(e)})

            if path == '/api/youtube/auth/client-secrets':
                from veraxi_ymmp.youtube_auth import save_client_secrets, get_auth_status
                raw_secrets = body.get("client_secrets_json") or body.get("client_secrets") or body
                try:
                    save_client_secrets(raw_secrets)
                    return self.send_json(200, {"success": True, "status": get_auth_status()})
                except ValueError as ve:
                    return self.send_json(400, {"error": str(ve)})
                except Exception as ex:
                    return self.send_json(500, {"error": str(ex)})

            if path == '/api/youtube/auth/connect':
                from veraxi_ymmp.youtube_auth import authenticate_youtube, resolve_client_secrets_path, get_auth_status
                secrets_path = resolve_client_secrets_path()
                if not secrets_path or not secrets_path.exists():
                    return self.send_json(400, {"error": "client_secrets.json is not configured. Please save client secrets first."})
                try:
                    authenticate_youtube(client_secrets_path=secrets_path, no_browser=False)
                    status = get_auth_status()
                    try:
                        from veraxi_ymmp.youtube_adapter import YouTubeAdapter
                        status["channel"] = YouTubeAdapter().get_channel_info()
                    except Exception as ch_err:
                        logger.debug(f"Could not retrieve channel info after connect: {ch_err}")
                    return self.send_json(200, {"success": True, "status": status})
                except Exception as ex:
                    return self.send_json(500, {"error": str(ex)})

            if path == '/api/youtube/auth/revoke':
                from veraxi_ymmp.youtube_auth import revoke_token, get_auth_status
                revoked = revoke_token()
                return self.send_json(200, {"success": revoked, "status": get_auth_status()})

            self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"POST error: {e}", exc_info=True)
            self.send_json(500, {"error": str(e)})

    def do_PUT(self) -> None:
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            try:
                body = json.loads(post_data)
            except json.JSONDecodeError:
                body = {}

            match = re.match(r'^/api/projects/([^/]+)/script$', path)
            if match:
                project_name = urllib.parse.unquote(match.group(1))
                script = body.get("script")
                broll_manifest = body.get("broll_manifest")

                script_json = json.dumps(script) if script is not None else "[]"
                broll_json = json.dumps(broll_manifest) if broll_manifest is not None else None

                res = save_project_script(_project_rel_path(project_name), script_json, broll_json)
                if not res.get("success"):
                    return self.send_json(422, res)
                return self.send_json(200, res)

            self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"PUT error: {e}", exc_info=True)
            self.send_json(500, {"error": str(e)})


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type in (ConnectionResetError, BrokenPipeError):
            return  # Normal client disconnect
        logger.error(f"Socket error for {client_address}: {exc_val}")


def serve(port: int = 8000) -> None:
    server_address = ('127.0.0.1', port)
    httpd = ThreadingHTTPServer(server_address, APIHandler)
    logger.info(f"Starting Veraxi YMMP API server on http://127.0.0.1:{port}")
    try:
        while True:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                logger.info("Shutting down API server")
                break
            except Exception as e:
                logger.error(f"API server loop recovered from exception: {e}", exc_info=True)
                time.sleep(0.5)
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
