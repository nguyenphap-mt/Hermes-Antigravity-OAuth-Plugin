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

try:
    from tools.antigravity_bridge.auth import (
        AntigravityAuthManager,
        get_hermes_dir,
    )
    from tools.antigravity_bridge.client import (
        ANTIGRAVITY_SUPPORTED_MODELS,
        AntigravityClient,
    )
except ImportError:
    from .auth import (
        AntigravityAuthManager,
        get_hermes_dir,
    )
    from .client import (
        ANTIGRAVITY_SUPPORTED_MODELS,
        AntigravityClient,
    )

try:
    from tools.antigravity_bridge.models import ModelDiscoveryManager
except ImportError:
    from .models import ModelDiscoveryManager

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


class AntigravityBridgeServer:
    """Async HTTP Server exposing Antigravity Code Assist as OpenAI API."""

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        auth_manager: Optional[AntigravityAuthManager] = None,
        model_discovery: Optional[ModelDiscoveryManager] = None,
    ) -> None:
        os.environ["ANTIGRAVITY_IN_BRIDGE_SERVER"] = "1"
        self.host = host
        self.port = port
        self.auth_manager = auth_manager or AntigravityAuthManager()
        self.model_discovery = model_discovery or ModelDiscoveryManager(
            self.auth_manager, is_bridge_server=True
        )
        self.model_discovery.is_bridge_server = True
        self.client = AntigravityClient(self.auth_manager, self.model_discovery)
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/auth/status", self.handle_auth_status)
        self.app.router.add_post("/auth/login", self.handle_auth_login)
        self.app.router.add_get("/v1/models", self.handle_list_models)
        self.app.router.add_get("/v1/quota", self.handle_quota)
        self.app.router.add_post("/v1/chat/completions", self.handle_chat_completions)
        self.app.router.add_post("/v1/embeddings", self.handle_embeddings)

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
        if request.headers.get("X-Antigravity-Internal-Probe") == "1":
            cached = self.model_discovery._load_cache_from_disk()
            raw = cached.get("models", {}) if cached else self.model_discovery._fallback_models()
            data = [
                {"id": mid, "object": "model", "owned_by": "antigravity", **(m if isinstance(m, dict) else {})}
                for mid, m in raw.items()
            ]
            return web.json_response({"object": "list", "data": data})

        force_refresh = request.query.get("refresh", "").lower() in {"1", "true", "yes"}
        models = await asyncio.to_thread(self.model_discovery.list_openai_models, force_refresh=force_refresh)
        return web.json_response({
            "object": "list",
            "data": models,
        })

    async def handle_quota(self, request: web.Request) -> web.Response:
        force_refresh = request.query.get("refresh", "").lower() in {"1", "true", "yes"}
        quota_data = await asyncio.to_thread(self.model_discovery.fetch_quota_summary, force_refresh=force_refresh)
        return web.json_response(quota_data)

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
                status_code = 429 if "429" in str(e) or "exhausted" in str(e).lower() else (403 if "403" in str(e) else 500)
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
                status_code = 429 if "429" in str(e) or "exhausted" in str(e).lower() else (403 if "403" in str(e) else 500)
                err_type = "rate_limit_error" if status_code == 429 else "api_error"
                return web.json_response(
                    {"error": {"message": str(e), "type": err_type, "code": status_code}},
                    status=status_code,
                )

    async def handle_embeddings(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception as e:
            return web.json_response(
                {"error": {"message": f"Invalid JSON payload: {e}", "type": "invalid_request_error"}},
                status=400,
            )

        inp = payload.get("input", "")
        if isinstance(inp, str):
            texts = [inp]
        elif isinstance(inp, list):
            texts = [str(x) for x in inp]
        else:
            texts = [str(inp)]

        model = payload.get("model", "bge-small-en-v1.5")

        def _get_vectors(t_list):
            try:
                import numpy as np
                import onnxruntime as ort
                from tokenizers import Tokenizer

                if not hasattr(self, "_ort_session") or self._ort_session is None:
                    model_dir = get_hermes_dir() / "models" / "bge-small-en-v1.5"
                    model_dir.mkdir(parents=True, exist_ok=True)
                    onnx_path = model_dir / "model_quantized.onnx"
                    tok_path = model_dir / "tokenizer.json"
                    if not onnx_path.exists() or not tok_path.exists():
                        import urllib.request
                        base_hf = "https://huggingface.co/Xenova/bge-small-en-v1.5/resolve/main"
                        if not onnx_path.exists():
                            urllib.request.urlretrieve(f"{base_hf}/onnx/model_quantized.onnx", onnx_path)
                        if not tok_path.exists():
                            urllib.request.urlretrieve(f"{base_hf}/tokenizer.json", tok_path)
                    tok = Tokenizer.from_file(str(tok_path))
                    tok.enable_truncation(max_length=512)
                    tok.enable_padding(length=512)
                    opts = ort.SessionOptions()
                    opts.intra_op_num_threads = 4
                    opts.inter_op_num_threads = 2
                    self._ort_tokenizer = tok
                    self._ort_session = ort.InferenceSession(
                        str(onnx_path),
                        sess_options=opts,
                        providers=["CPUExecutionProvider"],
                    )
                encoded = self._ort_tokenizer.encode_batch(t_list)
                input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
                att_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
                inputs = {"input_ids": input_ids, "attention_mask": att_mask}
                for m_in in self._ort_session.get_inputs():
                    if m_in.name == "token_type_ids":
                        inputs["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)
                out = self._ort_session.run(None, inputs)[0]
                if out.ndim == 3:
                    mask_exp = np.expand_dims(att_mask, -1).astype(np.float32)
                    out = np.sum(out * mask_exp, axis=1) / np.clip(mask_exp.sum(axis=1), 1e-9, None)
                norms = np.clip(np.linalg.norm(out, ord=2, axis=1, keepdims=True), 1e-9, None)
                normalized = (out / norms).astype(np.float32)
                return [row.tolist() for row in normalized]
            except Exception as ex:
                logger.error("Embedding error: %s", ex)
                return [[0.0] * 384 for _ in t_list]

        vectors = await asyncio.to_thread(_get_vectors, texts)

        data = []
        total_tokens = 0
        for i, vec in enumerate(vectors):
            data.append({
                "object": "embedding",
                "index": i,
                "embedding": [float(val) for val in vec],
            })
            total_tokens += max(1, len(texts[i].split()))

        return web.json_response({
            "object": "list",
            "data": data,
            "model": model,
            "usage": {
                "prompt_tokens": total_tokens,
                "total_tokens": total_tokens,
            },
        })

    async def start(self) -> web.AppRunner:
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("Antigravity Bridge Server listening on http://%s:%s", self.host, self.port)
        return runner


def run_server(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> None:
    """Run the bridge server with asyncio event loop."""
    import asyncio
    import os
    pid_file = get_pid_file()
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    async def _serve():
        server = AntigravityBridgeServer(host=host, port=port)
        runner = await server.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()
            try:
                if pid_file.exists():
                    pid_file.unlink(missing_ok=True)
            except Exception:
                pass

    try:
        asyncio.run(_serve())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            if pid_file.exists():
                pid_file.unlink(missing_ok=True)
        except Exception:
            pass


def is_server_running(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> bool:
    """Check if the bridge server is responding to health checks."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://{host}:{port}/health")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("bridge") == "antigravity"
    except Exception:
        return False


def ensure_antigravity_bridge_running(
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    timeout: float = 4.0,
) -> bool:
    """Ensure the Antigravity bridge server is running, spawning a daemon if not."""
    if is_server_running(host=host, port=port):
        return True

    import subprocess
    import sys
    import time
    from pathlib import Path

    try:
        try:
            from tools.antigravity_bridge.auth import AntigravityAuthManager
        except ImportError:
            from .auth import AntigravityAuthManager
        mgr = AntigravityAuthManager()
        if not mgr.load_all_stored_credentials():
            logger.debug("Antigravity bridge auto-spawn skipped: no stored credentials")
            return False
    except Exception as ex:
        logger.debug("Antigravity bridge auth check failed: %s", ex)
        return False

    plugin_root = Path(__file__).resolve().parent.parent
    log_file = get_log_file()
    safe_root = repr(str(plugin_root))
    safe_log = repr(str(log_file))
    safe_host = repr(str(host))
    safe_port = int(port)

    runner_code = (
        f"import sys, os\n"
        f"p = {safe_root}\n"
        f"if p not in sys.path: sys.path.insert(0, p)\n"
        f"try:\n"
        f"    log_fd = open({safe_log}, 'a', encoding='utf-8')\n"
        f"    sys.stdout = log_fd\n"
        f"    sys.stderr = log_fd\n"
        f"except Exception:\n"
        f"    pass\n"
        f"try:\n"
        f"    from tools.antigravity_bridge.server import run_server\n"
        f"except ImportError:\n"
        f"    from bridge.server import run_server\n"
        f"run_server(host={safe_host}, port={safe_port})\n"
    )

    try:
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            try:
                subprocess.Popen(
                    [sys.executable, "-u", "-c", runner_code],
                    creationflags=flags | 0x01000000,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            except OSError:
                subprocess.Popen(
                    [sys.executable, "-u", "-c", runner_code],
                    creationflags=flags,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
        else:
            subprocess.Popen(
                [sys.executable, "-u", "-c", runner_code],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.2)
            if is_server_running(host=host, port=port):
                logger.info("Antigravity Bridge auto-started on http://%s:%s", host, port)
                return True
        return is_server_running(host=host, port=port)
    except Exception as e:
        logger.warning("Failed to auto-spawn Antigravity Bridge: %s", e)
        return False

