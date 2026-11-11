"""Interactive In-Dashboard Browser Sign-In Manager for Gemini Web App.

Allows operators on remote servers (VPS) or mobile browsers to complete standard
Google Sign-In directly inside the Dashboard modal and persist the resulting
`gemini.google.com/app` session into `GeminiWebPoolManager`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .pool_manager import GeminiWebPoolManager
from .session_manager import (
    DEFAULT_USER_AGENT,
    get_hermes_dir,
    is_allowed_gemini_web_cookie_domain,
    is_synthetic_oauth_cookie,
)

logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1024
VIEWPORT_HEIGHT = 680
SESSION_MAX_LIFETIME_SEC = 300.0
SESSION_IDLE_TIMEOUT_SEC = 180.0

ALLOWED_LOGIN_HOST_SUFFIXES = (
    ".google.com",
    "google.com",
    ".gstatic.com",
    "gstatic.com",
    ".googleapis.com",
    "googleapis.com",
    ".googleusercontent.com",
    "googleusercontent.com",
    ".youtube.com",
    "youtube.com",
)

KEY_CODE_MAP: Dict[str, Tuple[int, str]] = {
    "Enter": (13, "Enter"),
    "Backspace": (8, "Backspace"),
    "Tab": (9, "Tab"),
    "Escape": (27, "Escape"),
    "Delete": (46, "Delete"),
    "ArrowLeft": (37, "ArrowLeft"),
    "ArrowUp": (38, "ArrowUp"),
    "ArrowRight": (39, "ArrowRight"),
    "ArrowDown": (40, "ArrowDown"),
}


def build_google_service_login_url(email: str = "") -> str:
    """Construct the Google Sign-In URL redirecting to gemini.google.com/app."""
    params: Dict[str, str] = {
        "continue": "https://gemini.google.com/app?hl=vi",
        "hl": "vi",
    }
    clean_email = (email or "").strip()
    if clean_email:
        params["Email"] = clean_email
    return f"https://accounts.google.com/ServiceLogin?{urllib.parse.urlencode(params)}"


def is_allowed_login_url(url: str) -> bool:
    """Allow only Google sign-in and Gemini Web origins inside the login view."""
    raw = (url or "").strip()
    if not raw or raw in ("about:blank", "chrome://newtab/", "data:,"):
        return True
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return False
    if parsed.scheme not in ("https", "http"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return any(
        host == suffix or (suffix.startswith(".") and host.endswith(suffix))
        for suffix in ALLOWED_LOGIN_HOST_SUFFIXES
    )


def find_chromium_binary(hermes_dir: Optional[Path] = None) -> Optional[str]:
    """Locate an installed Chromium, Chrome, or Edge binary across Linux, Windows, and macOS."""
    env_bin = os.environ.get("HERMES_CHROME_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin

    base_dir = hermes_dir or get_hermes_dir()
    search_roots = [
        base_dir / "tools",
        Path.home() / ".hermes" / "tools",
        Path.home() / ".cache" / "ms-playwright",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        search_roots.append(Path(local_app_data) / "ms-playwright")

    rel_patterns = (
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-win/chrome.exe",
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    )
    for root in search_roots:
        if not root.is_dir():
            continue
        for pat in rel_patterns:
            matches = sorted(root.glob(pat), reverse=True)
            for m in matches:
                if m.is_file():
                    return str(m)

    for cmd_name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "msedge",
    ):
        found = shutil.which(cmd_name)
        if found:
            return found

    os_paths: List[Path] = []
    if sys.platform == "win32":
        prog = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        if local_app_data:
            os_paths.append(Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe")
        os_paths.extend(
            [
                Path(prog) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(prog86) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(prog) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(prog86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ]
        )
    elif sys.platform == "darwin":
        os_paths.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            ]
        )

    for p in os_paths:
        if p.is_file():
            return str(p)
    return None


def _allocate_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _CDPPageSession:
    """Lightweight async DevTools WebSocket client over aiohttp."""

    def __init__(self, http_session: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._http = http_session
        self._ws = ws
        self._next_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task = asyncio.create_task(self._read_loop())
        self.closed = False

    async def _read_loop(self) -> None:
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        continue
                    msg_id = data.get("id")
                    if msg_id is not None and msg_id in self._pending:
                        fut = self._pending.pop(msg_id)
                        if not fut.done():
                            if "error" in data:
                                fut.set_result({})
                            else:
                                fut.set_result(data.get("result") or {})
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except Exception:
            pass
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_result({})
            self._pending.clear()

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 12.0) -> Dict[str, Any]:
        if self.closed or self._ws.closed:
            return {}
        self._next_id += 1
        cur_id = self._next_id
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[cur_id] = fut
        try:
            await self._ws.send_json({"id": cur_id, "method": method, "params": params or {}})
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self._pending.pop(cur_id, None)
            return {}

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        try:
            await self._ws.close()
        except Exception:
            pass
        try:
            await self._http.close()
        except Exception:
            pass


@dataclass
class _ActiveLoginContext:
    session_id: str
    email: str
    node_id: str
    profile_dir: Path
    proc: Any
    cdp: Any
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    status: str = "awaiting_login"
    current_url: str = ""
    last_image_b64: str = ""
    completed: bool = False
    completed_node: Optional[Dict[str, Any]] = None
    completed_message: str = ""
    error: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class GeminiWebBrowserLoginManager:
    """Manages short-lived interactive Google Sign-In browser sessions for Dashboard users."""

    def __init__(self, hermes_dir: Optional[Path] = None) -> None:
        self.hermes_dir = hermes_dir or get_hermes_dir()
        self._sessions: Dict[str, _ActiveLoginContext] = {}

    async def _cleanup_expired_sessions(self) -> None:
        now = time.time()
        to_close: List[str] = []
        for sid, ctx in list(self._sessions.items()):
            if ctx.completed:
                if now - ctx.last_active_at > 60.0:
                    to_close.append(sid)
                continue
            if (
                now - ctx.created_at > SESSION_MAX_LIFETIME_SEC
                or now - ctx.last_active_at > SESSION_IDLE_TIMEOUT_SEC
            ):
                to_close.append(sid)
        for sid in to_close:
            await self.stop_session(sid)

    async def _terminate_context(self, ctx: _ActiveLoginContext) -> None:
        if ctx.cdp is not None:
            try:
                await ctx.cdp.close()
            except Exception:
                pass
            ctx.cdp = None
        proc = ctx.proc
        ctx.proc = None
        if proc is not None:
            try:
                if sys.platform != "win32" and hasattr(os, "killpg"):
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        proc.terminate()
                else:
                    proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
            except Exception:
                pass
        if ctx.profile_dir and ctx.profile_dir.exists():
            shutil.rmtree(ctx.profile_dir, ignore_errors=True)

    async def _spawn_browser_and_connect_cdp(
        self,
        email: str,
        port: int,
        profile_dir: Path,
    ) -> Tuple[Any, _CDPPageSession]:
        chrome_bin = find_chromium_binary(self.hermes_dir)
        if not chrome_bin:
            raise RuntimeError(
                "Không tìm thấy trình duyệt Chromium/Chrome trên máy chủ để mở khung đăng nhập trực tiếp."
            )

        target_url = build_google_service_login_url("")
        chrome_args = [
            chrome_bin,
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-popup-blocking",
            "--disable-notifications",
            "--disable-sync",
            "--disable-translate",
            "--password-store=basic",
            "--use-mock-keychain",
            "--lang=vi-VN",
            f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
        ]

        use_xvfb = sys.platform.startswith("linux") and bool(shutil.which("xvfb-run"))
        if use_xvfb:
            cmd = [
                "xvfb-run",
                "-a",
                f"--server-args=-screen 0 {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}x24",
                *chrome_args,
                target_url,
            ]
        else:
            cmd = [
                *chrome_args,
                "--headless=new",
                f"--user-agent={DEFAULT_USER_AGENT}",
                target_url,
            ]

        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **popen_kwargs)
        http_session = aiohttp.ClientSession()
        ws_url: Optional[str] = None
        try:
            for _ in range(32):
                await asyncio.sleep(0.4)
                if proc.poll() is not None:
                    _, err_bytes = proc.communicate()
                    err_txt = (err_bytes or b"").decode("utf-8", errors="ignore")[:300]
                    raise RuntimeError(f"Trình duyệt đăng nhập thoát sớm (code {proc.returncode}): {err_txt}")
                try:
                    async with http_session.get(
                        f"http://127.0.0.1:{port}/json/list",
                        timeout=aiohttp.ClientTimeout(total=1.5),
                    ) as resp:
                        if resp.status == 200:
                            pages = await resp.json()
                            for p in pages:
                                if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
                                    ws_url = p["webSocketDebuggerUrl"]
                                    break
                            if ws_url:
                                break
                except Exception:
                    pass

            if not ws_url:
                raise RuntimeError("Không thể kết nối cổng điều khiển trình duyệt nội bộ (CDP timeout).")

            ws = await http_session.ws_connect(ws_url, max_msg_size=16 * 1024 * 1024)
            cdp = _CDPPageSession(http_session, ws)
            await cdp.send("Page.enable")
            await cdp.send("Runtime.enable")
            await cdp.send("Network.enable")
            await cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": VIEWPORT_WIDTH,
                    "height": VIEWPORT_HEIGHT,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )

            # Allow Google Sign-In Wiz controllers to finish hydrating before interacting
            await asyncio.sleep(2.0)
            return proc, cdp
        except Exception:
            await http_session.close()
            try:
                if sys.platform != "win32" and hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
            raise

    async def start_session(
        self,
        email: str = "",
        node_id: str = "",
        pool: Optional[GeminiWebPoolManager] = None,
    ) -> Dict[str, Any]:
        """Launch a fresh interactive Google Sign-In session (closing any active previous session)."""
        await self._cleanup_expired_sessions()
        # Keep max 1 concurrent interactive browser session to protect server RAM
        for active_sid, active_ctx in list(self._sessions.items()):
            if not active_ctx.completed:
                await self.stop_session(active_sid)

        session_id = f"gweb_bl_{int(time.time() * 1000)}"
        profile_dir = Path(tempfile.mkdtemp(prefix="hermes_gweb_login_"))
        port = _allocate_free_port()

        try:
            proc, cdp = await self._spawn_browser_and_connect_cdp(
                email=email,
                port=port,
                profile_dir=profile_dir,
            )
        except Exception as e:
            shutil.rmtree(profile_dir, ignore_errors=True)
            logger.warning("Failed starting interactive Gemini Web login browser: %s", e)
            return {
                "ok": False,
                "error": str(e),
                "message": str(e),
            }

        ctx = _ActiveLoginContext(
            session_id=session_id,
            email=(email or "").strip(),
            node_id=(node_id or "").strip(),
            profile_dir=profile_dir,
            proc=proc,
            cdp=cdp,
        )
        self._sessions[session_id] = ctx
        state = await self._refresh_and_build_state(ctx, pool=pool)
        if (
            ctx.email
            and not state.get("completed")
            and state.get("active_input_type") != "password"
            and "/signin/challenge/" not in str(state.get("current_url", ""))
        ):
            state = await self.send_action(
                session_id=session_id,
                action_type="submit_text",
                text=ctx.email,
                pool=pool,
            )
            for _ in range(6):
                if state.get("completed") or state.get("active_input_type") == "password" or "/signin/challenge/" in str(state.get("current_url", "")):
                    break
                await asyncio.sleep(0.35)
                state = await self.get_state(session_id=session_id, pool=pool)
        return state

    async def _refresh_and_build_state(
        self,
        ctx: _ActiveLoginContext,
        pool: Optional[GeminiWebPoolManager] = None,
    ) -> Dict[str, Any]:
        ctx.last_active_at = time.time()
        if ctx.completed:
            return {
                "ok": True,
                "session_id": ctx.session_id,
                "status": "completed",
                "completed": True,
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
                "current_url": ctx.current_url,
                "image_b64": ctx.last_image_b64,
                "node": ctx.completed_node,
                "message": ctx.completed_message,
            }

        if ctx.cdp is None:
            return {
                "ok": False,
                "session_id": ctx.session_id,
                "status": "closed",
                "completed": False,
                "error": ctx.error or "Phiên trình duyệt đăng nhập đã đóng.",
            }

        eval_expr = (
            "(() => {"
            "  const href = String(location.href || '');"
            "  let snlm0e = '', cfb2h = '', fsid = '';"
            "  try {"
            "    if (window.WIZ_global_data) {"
            "      snlm0e = String(window.WIZ_global_data.SNlM0e || '');"
            "      cfb2h = String(window.WIZ_global_data.cfb2h || '');"
            "      fsid = String(window.WIZ_global_data.FdrFJe || '');"
            "    }"
            "  } catch (e) {}"
            "  const active = document.activeElement;"
            "  const inputType = active && active.tagName === 'INPUT' ? (active.type || 'text') : '';"
            "  return JSON.stringify({"
            "    url: href,"
            "    title: String(document.title || ''),"
            "    snlm0e: snlm0e,"
            "    cfb2h: cfb2h,"
            "    fsid: fsid,"
            "    inputType: inputType,"
            "    userAgent: navigator.userAgent"
            "  });"
            "})()"
        )
        meta_raw = await ctx.cdp.send("Runtime.evaluate", {"expression": eval_expr, "returnByValue": True})
        meta_str = meta_raw.get("result", {}).get("value") or "{}"
        try:
            meta = json.loads(meta_str) if isinstance(meta_str, str) else {}
        except Exception:
            meta = {}

        cur_url = str(meta.get("url") or "")
        ctx.current_url = cur_url

        # Enforce strict Google/Gemini origin whitelist
        if cur_url and not is_allowed_login_url(cur_url):
            safe_url = build_google_service_login_url(ctx.email)
            await ctx.cdp.send("Page.navigate", {"url": safe_url})
            await asyncio.sleep(0.5)
            cur_url = safe_url
            ctx.current_url = safe_url

        # Check if user has landed on authenticated gemini.google.com/app with SNlM0e
        parsed_host = (urllib.parse.urlparse(cur_url).hostname or "").lower()
        snlm0e = str(meta.get("snlm0e") or "").strip()

        if parsed_host == "gemini.google.com":
            html_res = await ctx.cdp.send(
                "Runtime.evaluate",
                {
                    "expression": "document.documentElement ? document.documentElement.outerHTML : ''",
                    "returnByValue": True,
                },
            )
            html_str = str(html_res.get("result", {}).get("value") or "")
            if not snlm0e and html_str:
                m_sn = re.search(r'"SNlM0e"\s*:\s*"([^"]+)"', html_str)
                if m_sn:
                    snlm0e = m_sn.group(1)

            if snlm0e and not is_synthetic_oauth_cookie(snlm0e):
                ck_res = await ctx.cdp.send("Network.getAllCookies")
                raw_cookies = ck_res.get("cookies") or []
                root_cks: Dict[str, str] = {}
                gemini_cks: Dict[str, str] = {}
                for item in raw_cookies:
                    if not isinstance(item, dict):
                        continue
                    c_name = str(item.get("name") or "").strip()
                    c_val = str(item.get("value") or "").strip()
                    c_dom = str(item.get("domain") or "").strip().lower()
                    if not c_name or not c_val or is_synthetic_oauth_cookie(c_val):
                        continue
                    if not is_allowed_gemini_web_cookie_domain(c_dom):
                        continue
                    if c_dom in ("gemini.google.com", ".gemini.google.com"):
                        gemini_cks[c_name] = c_val
                    else:
                        root_cks[c_name] = c_val

                merged_cookies = {**root_cks, **gemini_cks}
                if merged_cookies.get("__Secure-1PSID"):
                    active_pool = pool or GeminiWebPoolManager(hermes_dir=self.hermes_dir)
                    cfb2h = str(meta.get("cfb2h") or "")
                    fsid = str(meta.get("fsid") or "")
                    if not cfb2h and html_str:
                        m_cf = re.search(r'"cfb2h"\s*:\s*"([^"]+)"', html_str)
                        if m_cf:
                            cfb2h = m_cf.group(1)
                    if not fsid and html_str:
                        m_fs = re.search(r'"FdrFJe"\s*:\s*"([^"]+)"', html_str)
                        if m_fs:
                            fsid = m_fs.group(1)

                    node_info = active_pool.register_verified_browser_session(
                        cookies=merged_cookies,
                        snlm0e=snlm0e,
                        cfb2h=cfb2h,
                        fsid=fsid,
                        html=html_str,
                        user_agent=str(meta.get("userAgent") or DEFAULT_USER_AGENT),
                        requested_email=ctx.email,
                        requested_node_id=ctx.node_id,
                    )
                    ctx.completed = True
                    ctx.status = "completed"
                    ctx.completed_node = node_info
                    ctx.completed_message = (
                        f"Đã đăng nhập thành công Gemini Web: "
                        f"{node_info.get('email') or node_info.get('display_name')} "
                        f"({node_info.get('tier_badge', 'READY')})!"
                    )
                    await self._terminate_context(ctx)
                    return {
                        "ok": True,
                        "session_id": ctx.session_id,
                        "status": "completed",
                        "completed": True,
                        "width": VIEWPORT_WIDTH,
                        "height": VIEWPORT_HEIGHT,
                        "current_url": cur_url,
                        "image_b64": ctx.last_image_b64,
                        "node": node_info,
                        "pool": active_pool.get_dashboard_pool_snapshot(),
                        "message": ctx.completed_message,
                    }

        shot = await ctx.cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 72})
        img_b64 = str(shot.get("data") or "")
        if img_b64:
            ctx.last_image_b64 = img_b64

        remaining_sec = max(0, int(SESSION_MAX_LIFETIME_SEC - (time.time() - ctx.created_at)))
        return {
            "ok": True,
            "session_id": ctx.session_id,
            "status": "awaiting_login",
            "completed": False,
            "width": VIEWPORT_WIDTH,
            "height": VIEWPORT_HEIGHT,
            "current_url": cur_url,
            "active_input_type": str(meta.get("inputType") or ""),
            "remaining_seconds": remaining_sec,
            "image_b64": ctx.last_image_b64,
        }

    async def get_state(
        self,
        session_id: str,
        pool: Optional[GeminiWebPoolManager] = None,
    ) -> Dict[str, Any]:
        await self._cleanup_expired_sessions()
        ctx = self._sessions.get(session_id)
        if not ctx:
            return {
                "ok": False,
                "session_id": session_id,
                "status": "expired",
                "completed": False,
                "error": "Phiên đăng nhập trực tiếp đã hết thời gian chờ hoặc đã đóng.",
            }
        async with ctx.lock:
            return await self._refresh_and_build_state(ctx, pool=pool)

    async def send_action(
        self,
        session_id: str,
        action_type: str,
        x: float = 0.0,
        y: float = 0.0,
        text: str = "",
        key: str = "",
        delta_y: float = 0.0,
        clear_first: bool = True,
        press_enter: bool = True,
        pool: Optional[GeminiWebPoolManager] = None,
    ) -> Dict[str, Any]:
        ctx = self._sessions.get(session_id)
        if not ctx:
            return {
                "ok": False,
                "session_id": session_id,
                "status": "expired",
                "completed": False,
                "error": "Phiên đăng nhập đã đóng. Vui lòng bấm Mở lại trình duyệt.",
            }

        async with ctx.lock:
            if ctx.completed or ctx.cdp is None:
                return await self._refresh_and_build_state(ctx, pool=pool)

            act = (action_type or "").strip().lower()
            settle_sec = 0.15

            if act == "click":
                cx = max(0, min(VIEWPORT_WIDTH, int(round(x))))
                cy = max(0, min(VIEWPORT_HEIGHT, int(round(y))))
                await ctx.cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx, "y": cy})
                await ctx.cdp.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": cx, "y": cy, "button": "left", "clickCount": 1},
                )
                await ctx.cdp.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1},
                )
                settle_sec = 0.35

            elif act == "submit_text":
                # Focus active or primary visible input box, optionally select existing value, insert text, and hit Enter
                focus_js = (
                    "(() => {"
                    "  let el = document.activeElement;"
                    "  if (!el || (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && !el.isContentEditable)) {"
                    "    const candidates = Array.from(document.querySelectorAll("
                    "      'input[type=\"password\"], input[type=\"email\"], input[type=\"tel\"], input[type=\"number\"], input[type=\"text\"], input:not([type=\"hidden\"])'"
                    "    ));"
                    "    el = candidates.find(i => !i.disabled && i.offsetParent !== null) || candidates[0];"
                    "    if (el) el.focus();"
                    "  }"
                    f"  if ({'true' if clear_first else 'false'} && el && typeof el.select === 'function') {{"
                    "    try { el.select(); } catch (e) {}"
                    "  }"
                    "  return Boolean(el);"
                    "})()"
                )
                await ctx.cdp.send("Runtime.evaluate", {"expression": focus_js, "returnByValue": True})
                if text:
                    await ctx.cdp.send("Input.insertText", {"text": text})
                if press_enter:
                    await asyncio.sleep(0.08)
                    next_btn_res = await ctx.cdp.send(
                        "Runtime.evaluate",
                        {
                            "expression": (
                                "(() => {"
                                "  const b = document.querySelector('#passwordNext button, #identifierNext button, #totpNext button, #idvPreregisteredPhoneNext button');"
                                "  if (!b) return '';"
                                "  const r = b.getBoundingClientRect();"
                                "  if (!r || !r.width || !r.height) return '';"
                                "  return Math.round(r.left + r.width / 2) + ',' + Math.round(r.top + r.height / 2);"
                                "})()"
                            ),
                            "returnByValue": True,
                        },
                    )
                    next_coords = str(next_btn_res.get("result", {}).get("value") or "").strip()
                    if re.fullmatch(r"\d+,\d+", next_coords):
                        nx_s, ny_s = next_coords.split(",", 1)
                        nx, ny = int(nx_s), int(ny_s)
                        await ctx.cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": nx, "y": ny})
                        await ctx.cdp.send(
                            "Input.dispatchMouseEvent",
                            {"type": "mousePressed", "x": nx, "y": ny, "button": "left", "clickCount": 1},
                        )
                        await ctx.cdp.send(
                            "Input.dispatchMouseEvent",
                            {"type": "mouseReleased", "x": nx, "y": ny, "button": "left", "clickCount": 1},
                        )
                    else:
                        await ctx.cdp.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyDown",
                                "key": "Enter",
                                "code": "Enter",
                                "text": "\r",
                                "unmodifiedText": "\r",
                                "windowsVirtualKeyCode": 13,
                                "nativeVirtualKeyCode": 13,
                            },
                        )
                        await ctx.cdp.send(
                            "Input.dispatchKeyEvent",
                            {
                                "type": "keyUp",
                                "key": "Enter",
                                "code": "Enter",
                                "windowsVirtualKeyCode": 13,
                                "nativeVirtualKeyCode": 13,
                            },
                        )
                settle_sec = 0.85

            elif act == "type":
                if text:
                    await ctx.cdp.send("Input.insertText", {"text": text})

            elif act == "clear_input":
                clear_js = (
                    "(() => {"
                    "  const el = document.activeElement;"
                    "  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {"
                    "    el.value = '';"
                    "    el.dispatchEvent(new Event('input', { bubbles: true }));"
                    "    return true;"
                    "  }"
                    "  return false;"
                    "})()"
                )
                await ctx.cdp.send("Runtime.evaluate", {"expression": clear_js, "returnByValue": True})

            elif act == "key":
                vk, code = KEY_CODE_MAP.get(key, (0, key))
                if vk:
                    down_payload: Dict[str, Any] = {
                        "type": "keyDown" if key == "Enter" else "rawKeyDown",
                        "key": key,
                        "code": code,
                        "windowsVirtualKeyCode": vk,
                        "nativeVirtualKeyCode": vk,
                    }
                    if key == "Enter":
                        down_payload["text"] = "\r"
                        down_payload["unmodifiedText"] = "\r"
                    await ctx.cdp.send("Input.dispatchKeyEvent", down_payload)
                    await ctx.cdp.send(
                        "Input.dispatchKeyEvent",
                        {
                            "type": "keyUp",
                            "key": key,
                            "code": code,
                            "windowsVirtualKeyCode": vk,
                            "nativeVirtualKeyCode": vk,
                        },
                    )
                    if key == "Enter":
                        settle_sec = 0.65

            elif act == "scroll":
                cx = max(0, min(VIEWPORT_WIDTH, int(round(x or (VIEWPORT_WIDTH / 2)))))
                cy = max(0, min(VIEWPORT_HEIGHT, int(round(y or (VIEWPORT_HEIGHT / 2)))))
                await ctx.cdp.send(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseWheel",
                        "x": cx,
                        "y": cy,
                        "deltaX": 0,
                        "deltaY": float(delta_y or 240.0),
                    },
                )

            elif act == "reload":
                await ctx.cdp.send("Page.reload")
                settle_sec = 0.6

            await asyncio.sleep(settle_sec)
            return await self._refresh_and_build_state(ctx, pool=pool)

    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        ctx = self._sessions.pop(session_id, None)
        if ctx is not None:
            await self._terminate_context(ctx)
        return {"ok": True, "session_id": session_id, "stopped": True}


_SHARED_BROWSER_LOGIN_MANAGER: Optional[GeminiWebBrowserLoginManager] = None


def get_shared_browser_login_manager(hermes_dir: Optional[Path] = None) -> GeminiWebBrowserLoginManager:
    global _SHARED_BROWSER_LOGIN_MANAGER
    target_dir = (hermes_dir or get_hermes_dir()).resolve()
    if (
        _SHARED_BROWSER_LOGIN_MANAGER is None
        or _SHARED_BROWSER_LOGIN_MANAGER.hermes_dir.resolve() != target_dir
    ):
        _SHARED_BROWSER_LOGIN_MANAGER = GeminiWebBrowserLoginManager(hermes_dir=target_dir)
    return _SHARED_BROWSER_LOGIN_MANAGER
