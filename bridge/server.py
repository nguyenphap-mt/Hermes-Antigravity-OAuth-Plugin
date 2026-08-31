"""HTTP server and daemon runner for Antigravity Local Bridge.

Implements standard OpenAI API endpoints:
- GET  /v1/models
- POST /v1/chat/completions (with Server-Sent Events streaming support)
- GET  /health
- GET  /auth/status
- POST /auth/login
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web

from .auth import (
    AntigravityAuthManager,
    get_hermes_dir,
)
from .client import (
    ANTIGRAVITY_SUPPORTED_MODELS,
    AntigravityClient,
)

logger = logging.getLogger(__name__)

DEFAULT_BRIDGE_PORT = 8100
DEFAULT_BRIDGE_HOST = "127.0.0.1"


def get_bridge_dir() -> Path:
    bridge_dir = get_hermes_dir() / "bridge" / "antigravity"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    return bridge_dir


def get_pid_file() -> Path:
    return get_bridge_dir() / "bridge.pid"


def get_log_file() -> Path:
    log_dir = get_hermes_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "antigravity_bridge.log"


# Bug #15 fix: named subprocess flag constants instead of magic hex.
_WIN_DETACHED_PROCESS = 0x00000008
_WIN_CREATE_NEW_PROCESS_GROUP = 0x00000200
_WIN_CREATE_BREAKAWAY_FROM_JOB = 0x01000000


class AntigravityBridgeServer:
    """Async HTTP Server exposing Antigravity Code Assist as OpenAI API."""

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        auth_manager: Optional[AntigravityAuthManager] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_manager = auth_manager or AntigravityAuthManager()
        self.client = AntigravityClient(self.auth_manager)
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/auth/status", self.handle_auth_status)
        self.app.router.add_post("/auth/login", self.handle_auth_login)
        self.app.router.add_get("/v1/models", self.handle_list_models)
        self.app.router.add_post("/v1/chat/completions", self.handle_chat_completions)

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "bridge": "antigravity",
            "version": "1.0.0",
            "timestamp": time.time(),
        })

    async def handle_auth_status(self, request: web.Request) -> web.Response:
        creds = self.auth_manager.load_stored_credentials() or self.auth_manager.discover_local_tokens()
        if not creds:
            return web.json_response({
                "logged_in": False,
                "email": "",
                "project_id": "",
                "expires_at": None,
                "message": "No credentials stored. Please log in.",
            })

        return web.json_response({
            "logged_in": True,
            "email": creds.email,
            "project_id": creds.project_id,
            "expires_at": creds.expires_at,
            "is_expired": creds.is_expired,
            "has_refresh_token": bool(creds.refresh_token),
            "source": creds.source,
        })

    async def handle_auth_login(self, request: web.Request) -> web.Response:
        try:
            creds = await asyncio.to_thread(self.auth_manager.login_pkce)
            return web.json_response({
                "ok": True,
                "email": creds.email,
                "project_id": creds.project_id,
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_list_models(self, request: web.Request) -> web.Response:
        models = []
        for m in ANTIGRAVITY_SUPPORTED_MODELS:
            models.append({
                "id": m["id"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "antigravity",
                "permission": [],
                "description": m.get("description", ""),
            })
        return web.json_response({
            "object": "list",
            "data": models,
        })

    async def handle_chat_completions(self, request: web.Request) -> web.StreamResponse:
        try:
            payload = await request.json()
        except Exception as e:
            return web.json_response(
                {"error": {"message": f"Invalid JSON payload: {e}", "type": "invalid_request_error"}},
                status=400,
            )

        auth_header = request.headers.get("Authorization") or ""
        bearer_token = ""
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header[7:].strip()
            if bearer_token in {"dummy", "none", "token", "default", "antigravity"}:
                bearer_token = ""

        is_stream = bool(payload.get("stream"))

        if is_stream:
            stream_gen = self.client.stream_chat_completion(payload, bearer_token=bearer_token)
            try:
                first_chunk = await stream_gen.__anext__()
            except Exception as e:
                logger.error("Error connecting to chat completion stream: %s", e)
                # Bug #11 fix: prefer httpx's structured response.status_code when available,
                # fall back to string parsing only for opaque errors.
                status_code = 500
                try:
                    status_code = e.response.status_code  # type: ignore[attr-defined]
                except AttributeError:
                    msg = str(e).lower()
                    if "429" in str(e) or "exhausted" in msg:
                        status_code = 429
                    elif "403" in str(e):
                        status_code = 403
                err_type = "rate_limit_error" if status_code == 429 else "api_error"
                return web.json_response(
                    {"error": {"message": str(e), "type": err_type, "code": status_code}},
                    status=status_code,
                )

            response = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            try:
                await response.prepare(request)
                await response.write(first_chunk.encode("utf-8"))
                try:
                    async for chunk_str in stream_gen:
                        await response.write(chunk_str.encode("utf-8"))
                except Exception as e:
                    logger.error("Error during chat completion stream: %s", e)
                await response.write_eof()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                logger.debug("Client disconnected during streaming: %s", e)
            except Exception as e:
                if "closing transport" in str(e).lower() or "connection" in str(e).lower():
                    logger.debug("Client connection lost during streaming: %s", e)
                else:
                    logger.error("Unexpected error during streaming: %s", e)
            return response
        else:
            try:
                result = await self.client.create_chat_completion(payload, bearer_token=bearer_token)
                return web.json_response(result)
            except Exception as e:
                logger.error("Error during chat completion: %s", e)
                status_code = 500
                try:
                    status_code = e.response.status_code  # type: ignore[attr-defined]
                except AttributeError:
                    msg = str(e).lower()
                    if "429" in str(e) or "exhausted" in msg:
                        status_code = 429
                    elif "403" in str(e):
                        status_code = 403
                err_type = "rate_limit_error" if status_code == 429 else "api_error"
                return web.json_response(
                    {"error": {"message": str(e), "type": err_type, "code": status_code}},
                    status=status_code,
                )

    async def start(self) -> web.AppRunner:
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("Antigravity Bridge Server listening on http://%s:%s", self.host, self.port)
        return runner


def run_server(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> None:
    """Run the bridge server in the foreground."""
    server = AntigravityBridgeServer(host=host, port=port)
    web.run_app(server.app, host=host, port=port)


def is_server_running(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> bool:
    """Check if the bridge server is responding to health checks."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://{host}:{port}/health")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Bug #13 fix: also verify status field is "ok" so degraded
            # servers don't report as running.
            return data.get("bridge") == "antigravity" and data.get("status") == "ok"
    except Exception:
        return False


def ensure_antigravity_bridge_running(
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    timeout: float = 3.0,
) -> bool:
    """Ensure the Antigravity bridge server is running, spawning a daemon if not."""
    if is_server_running(host=host, port=port):
        return True

    try:
        from .auth import AntigravityAuthManager
        mgr = AntigravityAuthManager()
        if not mgr.load_all_stored_credentials():
            return False
    except Exception:
        return False

    # Bug #12 fix: avoid string interpolation into python -c (potential code
    # injection). Pass host/port as JSON-encoded argv instead and parse inside.
    cmd = [
        sys.executable,
        "-u",
        "-c",
        (
            "import sys, json;"
            " cfg = json.loads(sys.argv[1]);"
            " sys.path.insert(0, cfg['cwd']);"
            " from antigravity_bridge.server import run_server;"
            " run_server(host=cfg['host'], port=cfg['port'])"
        ),
        "__ANTIGRAVITY_CONFIG__",  # placeholder argv[1]
    ]

    # Substitute the config safely via argv (no shell, no interpolation).
    import json as _json
    safe_cfg = _json.dumps({"host": host, "port": port, "cwd": str(get_bridge_dir() / "tools")})
    cmd[-1] = safe_cfg

    # Bug #14/15 fix: use named subprocess flags instead of magic hex, and
    # only write the PID file after the process is verified alive.
    try:
        if sys.platform == "win32":
            creationflags = (
                _WIN_DETACHED_PROCESS
                | _WIN_CREATE_NEW_PROCESS_GROUP
                | _WIN_CREATE_BREAKAWAY_FROM_JOB
            )
            proc = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )

        # Wait for server to actually come up before recording PID.
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_server_running(host=host, port=port):
                pid_file = get_pid_file()
                try:
                    pid_file.write_text(str(proc.pid), encoding="utf-8")
                except Exception as write_err:
                    logger.debug("Failed to write PID file: %s", write_err)
                logger.info("Antigravity Bridge auto-started on http://%s:%s", host, port)
                return True
            # If process already died, give up early.
            if proc.poll() is not None:
                logger.warning(
                    "Antigravity Bridge daemon exited immediately (code=%s)", proc.returncode
                )
                return False
            time.sleep(0.2)

        return is_server_running(host=host, port=port)
    except Exception as e:
        logger.warning("Failed to auto-spawn Antigravity Bridge: %s", e)
        return False


if __name__ == "__main__":
    # When invoked via `python -m antigravity_bridge.server`, read host/port
    # from env vars and start the server. Without this, daemon spawn would
    # import the module but never call run_server (it would exit immediately).
    import os as _os

    _host = _os.environ.get("BRIDGE_HOST", DEFAULT_BRIDGE_HOST)
    try:
        _port = int(_os.environ.get("BRIDGE_PORT", str(DEFAULT_BRIDGE_PORT)))
    except ValueError:
        _port = DEFAULT_BRIDGE_PORT
    run_server(host=_host, port=_port)