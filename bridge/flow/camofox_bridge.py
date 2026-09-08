"""CamofoxFlowBridge — Autonomous Google Flow Bridge using Camofox.

Replicates 100% of kodelyx/flow-agent's Chrome Extension functionality
without requiring a manual Chrome extension or keeping Chrome open:
1. Manages local Camofox anti-detect browser server.
2. Maintains persistent Google Flow session (labs.google/fx/tools/flow).
3. Evaluates reCAPTCHA Enterprise tokens (SiteKey: 6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV).
4. Executes API calls directly inside the Flow browser context.
5. Captures and manages Flow Bearer tokens (flowKey).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

_FLOW_PUBLIC_KEY_B64 = "QUl6YVN5QnRybTBvNWFiMWMtRWM4WnVMY0d0M29KQUE1Vld0M3BZ"


def _get_flow_public_api_key() -> str:
    return os.environ.get("GOOGLE_FLOW_API_KEY") or base64.b64decode(_FLOW_PUBLIC_KEY_B64).decode("utf-8")

logger = logging.getLogger("tools.antigravity_bridge.flow.camofox_bridge")

# Defaults
DEFAULT_CAMOFOX_URL = "http://127.0.0.1:9377"
FLOW_BASE_URL = "https://labs.google/"
FLOW_EDITOR_URL = "https://labs.google/fx/tools/flow/create"
FLOW_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

DEFAULT_USER_ID = "google_flow_user"
DEFAULT_SESSION_KEY = "google_flow_studio"


class CamofoxFlowBridge:
    """Autonomous bridge communicating with Google Flow via Camofox."""

    _active_tab_id: Optional[str] = None

    def __init__(
        self,
        base_url: str = DEFAULT_CAMOFOX_URL,
        user_id: str = DEFAULT_USER_ID,
        session_key: str = DEFAULT_SESSION_KEY,
        command_timeout: int = 45,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.session_key = session_key
        self.command_timeout = command_timeout
        self.tab_id: Optional[str] = None
        self._flow_key: Optional[str] = self._load_persisted_flow_key()
        self._lock = asyncio.Lock()

    @staticmethod
    def _load_persisted_flow_key() -> Optional[str]:
        """Load persisted Google Flow OAuth access token if available."""
        from pathlib import Path
        for h in [Path.home() / ".hermes", Path.home() / "AppData" / "Local" / "hermes", Path.home() / ".camofox"]:
            f = h / "auth" / "flow_token.json"
            if not f.is_file():
                f = h / "flow_token.json"
            if f.is_file():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("token"):
                        return data["token"]
                except Exception:
                    pass
        return None

    async def switch_user(self, new_user_id: str) -> None:
        """Switch active user profile in Camofox."""
        new_user_id = str(new_user_id).strip()
        if self.user_id != new_user_id:
            logger.info("Switching Camofox bridge user: %s -> %s", self.user_id, new_user_id)
            try:
                await self.close_tab()
            except Exception:
                pass
            self.user_id = new_user_id
            self.tab_id = None
            self._flow_key = None

    # ─── Server Lifecycle ───────────────────────────────────────────────

    def is_server_running(self) -> bool:
        """Check if Camofox server responds to /health."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def ensure_server(self, interactive_mode: str = "off") -> bool:
        """Ensure Camofox server is running, auto-starting if needed."""
        if self.is_server_running():
            return True

        home = Path(os.environ.get("USERPROFILE", "~")).expanduser()
        camofox_dir = home / ".hermes" / "camofox-browser"

        if not camofox_dir.exists():
            logger.error("Camofox directory not found at %s", camofox_dir)
            return False

        logger.info("Auto-starting Camofox server from %s (interactive=%s)...", camofox_dir, interactive_mode)
        env = os.environ.copy()
        if interactive_mode and interactive_mode != "off":
            env["CAMOFOX_INTERACTIVE"] = interactive_mode

        node_bin = camofox_dir / "bin" / "camofox-browser.js"
        cmd = ["node", str(node_bin)] if node_bin.exists() else ["npm", "start"]

        try:
            creationflags = 0
            if os.name == "nt":
                # DETACHED_PROCESS so server survives parent process
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008

            subprocess.Popen(
                cmd,
                cwd=str(camofox_dir),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                shell=(os.name == "nt" and cmd[0] == "npm"),
            )

            # Wait up to 20s for server to respond
            for _ in range(20):
                time.sleep(1)
                if self.is_server_running():
                    logger.info("Camofox server started successfully.")
                    return True
        except Exception as e:
            logger.error("Failed to start Camofox server: %s", e)

        return False

    # ─── Tab & Session Lifecycle ────────────────────────────────────────

    async def ensure_tab(self) -> str:
        """Ensure a persistent tab is open on Google Flow / Labs origin."""
        if not self.is_server_running():
            if not self.ensure_server():
                raise RuntimeError("Camofox server is not reachable and could not be started.")

        # Check instance or class-level cached tab
        candidate_tab = self.tab_id or CamofoxFlowBridge._active_tab_id
        if candidate_tab:
            self.tab_id = candidate_tab
            try:
                probe = await self.evaluate("window.location.href", timeout=5)
                if probe and ("labs.google" in probe or "flow.google" in probe or "google.com" in probe):
                    CamofoxFlowBridge._active_tab_id = self.tab_id
                    return self.tab_id
            except Exception:
                self.tab_id = None
                CamofoxFlowBridge._active_tab_id = None

        # Look for existing active tabs from Camofox before creating a new one
        try:
            tabs_resp = await asyncio.to_thread(
                requests.get,
                f"{self.base_url}/tabs?userId={self.user_id}",
                timeout=5,
            )
            if tabs_resp.status_code == 200:
                tabs_data = tabs_resp.json().get("tabs", [])
                for t in tabs_data:
                    url = t.get("url", "")
                    tid = t.get("tabId")
                    if tid and ("labs.google" in url or "flow.google" in url or "google.com" in url):
                        self.tab_id = tid
                        CamofoxFlowBridge._active_tab_id = tid
                        logger.info("Reusing existing Camofox tab %s (%s)", self.tab_id, url)
                        return self.tab_id
        except Exception as ex:
            logger.debug("Error probing existing Camofox tabs: %s", ex)

        # Look for existing tabs or create one with retries
        last_err = None
        for attempt in range(3):
            try:
                create_resp = await asyncio.to_thread(
                    requests.post,
                    f"{self.base_url}/tabs",
                    json={
                        "userId": self.user_id,
                        "sessionKey": self.session_key,
                        "url": FLOW_BASE_URL,
                    },
                    timeout=self.command_timeout,
                )
                if create_resp.status_code == 200:
                    data = create_resp.json()
                    self.tab_id = data.get("tabId")
                    CamofoxFlowBridge._active_tab_id = self.tab_id
                    logger.info("Established Camofox tab %s on %s", self.tab_id, FLOW_BASE_URL)
                    return self.tab_id
                last_err = f"{create_resp.status_code} {create_resp.text}"
            except Exception as ex:
                last_err = str(ex)
            await asyncio.sleep(2.0)

        raise RuntimeError(f"Failed to create Camofox tab after retries: {last_err}")

    async def evaluate(self, expression: str, timeout: int = 20) -> Any:
        """Evaluate arbitrary JavaScript inside the Flow tab with retry on navigation race."""
        last_resp = None
        for attempt in range(4):
            tab_id = self.tab_id
            if not tab_id:
                tab_id = await self.ensure_tab()

            resp = await asyncio.to_thread(
                requests.post,
                f"{self.base_url}/tabs/{tab_id}/evaluate",
                json={"userId": self.user_id, "expression": expression},
                timeout=timeout,
            )
            last_resp = resp
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result")
            if resp.status_code == 409 and attempt < 3:
                logger.debug("Camofox evaluate 409 (navigation race), retrying in 1.5s (attempt %d/4)...", attempt + 1)
                await asyncio.sleep(1.5)
                continue
            break
        raise RuntimeError(f"Camofox evaluate failed: {last_resp.status_code if last_resp else 'no response'} {last_resp.text if last_resp else ''}")

    async def navigate(self, url: str) -> None:
        """Navigate active tab to a new URL."""
        tab_id = self.tab_id
        if not tab_id:
            tab_id = await self.ensure_tab()

        resp = await asyncio.to_thread(
            requests.post,
            f"{self.base_url}/tabs/{tab_id}/navigate",
            json={"userId": self.user_id, "url": url},
            timeout=self.command_timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Camofox navigate failed: {resp.status_code} {resp.text}")

    # ─── Auth & Status Probing ──────────────────────────────────────────

    @staticmethod
    def _load_persisted_flow_email() -> str:
        """Load email associated with persisted flow token."""
        from pathlib import Path
        for h in [Path.home() / ".hermes", Path.home() / "AppData" / "Local" / "hermes", Path.home() / ".camofox"]:
            f = h / "auth" / "flow_token.json"
            if not f.is_file():
                f = h / "flow_token.json"
            if f.is_file():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("email"):
                        return data["email"]
                except Exception:
                    pass
        return ""

    async def check_status(self) -> dict:
        """Inspect current browser tab state to determine auth & readiness."""
        if not self.is_server_running():
            return {
                "server_running": False,
                "tab_connected": False,
                "logged_in": False,
                "error": "Camofox server is not running",
            }

        try:
            await self.ensure_tab()
            if not self._flow_key:
                self._flow_key = self._load_persisted_flow_key()

            info_json = await self.evaluate(
                """(() => {
                    const url = window.location.href;
                    const isGoogleAuth = url.includes('accounts.google.com');
                    const hasPrompt = Boolean(document.querySelector('textarea, [contenteditable="true"]'));
                    const hasAvatar = Boolean(document.querySelector('img[alt*="Google Account"], button[aria-label*="Google Account"]'));
                    const title = document.title;
                    const accountEl = document.querySelector('a[aria-label*="@"], button[aria-label*="@"], img[alt*="@"]');
                    let email = null;
                    if (accountEl) {
                        const raw = accountEl.getAttribute('aria-label') || accountEl.getAttribute('alt') || '';
                        const m = raw.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})/);
                        if (m) email = m[1];
                    }
                    return JSON.stringify({
                        url,
                        isGoogleAuth,
                        hasPrompt,
                        hasAvatar,
                        title,
                        email,
                        flowKey: window.__FLOW_KEY__ || null
                    });
                })()"""
            )
            info = json.loads(info_json) if isinstance(info_json, str) else (info_json or {})
            logged_in = bool(self._flow_key) or (not info.get("isGoogleAuth") and (info.get("hasPrompt") or info.get("hasAvatar") or "create" in info.get("url", "")))

            return {
                "server_running": True,
                "tab_connected": True,
                "tab_id": self.tab_id,
                "logged_in": logged_in,
                "is_auth_screen": info.get("isGoogleAuth", False),
                "url": info.get("url"),
                "email": info.get("email") or self._load_persisted_flow_email(),
                "flow_key_present": bool(info.get("flowKey") or self._flow_key),
            }
        except Exception as e:
            return {
                "server_running": True,
                "tab_connected": False,
                "logged_in": bool(self._flow_key),
                "email": self._load_persisted_flow_email(),
                "error": str(e),
            }

    # ─── reCAPTCHA Enterprise Execution ─────────────────────────────────

    async def get_recaptcha_token(self, action: str = "IMAGE_GENERATION") -> str:
        """Solve and extract a reCAPTCHA Enterprise token for the given action."""
        await self.ensure_tab()

        # Ensure current tab origin matches https://labs.google
        try:
            current_origin = await self.evaluate("window.location.origin", timeout=5)
            if current_origin != "https://labs.google":
                await self.navigate("https://labs.google/")
                await asyncio.sleep(2)
        except Exception as ex:
            logger.debug("Origin check warning before reCAPTCHA: %s", ex)

        script = f"""(async () => {{
            const SITE_KEY = '{FLOW_SITE_KEY}';
            const ACTION = '{action}';
            const getWin = () => window.wrappedJSObject || window;
            let w = getWin();

            // 1. Ensure reCAPTCHA Enterprise script tag is present in document
            if (!document.querySelector('script[src*="recaptcha/enterprise.js"]')) {{
                const s = document.createElement('script');
                s.src = 'https://www.google.com/recaptcha/enterprise.js?render=' + SITE_KEY;
                s.async = true;
                document.head.appendChild(s);
            }}

            // 2. Poll for grecaptcha.enterprise.execute to be ready
            let ready = false;
            for (let i = 0; i < 40; i++) {{
                w = getWin();
                if (w && w.grecaptcha && w.grecaptcha.enterprise && typeof w.grecaptcha.enterprise.execute === 'function') {{
                    ready = true;
                    break;
                }}
                await new Promise(r => setTimeout(r, 250));
            }}

            if (!ready) {{
                return JSON.stringify({{ error: "Timeout waiting for grecaptcha.enterprise script in Camofox" }});
            }}

            // 3. Execute directly
            try {{
                let opts = w.Object ? new w.Object() : {{}};
                opts.action = ACTION;
                const token = await w.grecaptcha.enterprise.execute(SITE_KEY, opts);
                if (token && typeof token === 'string' && token.length > 20) {{
                    return JSON.stringify({{ token: token }});
                }}
                return JSON.stringify({{ error: 'Invalid token received: ' + String(token) }});
            }} catch (err) {{
                return JSON.stringify({{ error: err.message || String(err) }});
            }}
        }})()"""

        res = await self.evaluate(script, timeout=35)
        parsed = json.loads(res) if isinstance(res, str) else (res or {})
        if "token" in parsed and parsed["token"]:
            logger.info("Obtained reCAPTCHA Enterprise token (len=%d) for action=%s", len(parsed["token"]), action)
            return parsed["token"]

        err = parsed.get("error", "Unknown error")
        logger.error("reCAPTCHA execution returned: %s", err)
        return ""

    # ─── API Request Execution ──────────────────────────────────────────

    async def api_request(
        self,
        endpoint: str,
        body: dict,
        captcha_action: str = "IMAGE_GENERATION",
        method: str = "POST",
        timeout: int = 90,
    ) -> dict:
        """Execute a Google Flow API request directly from the browser tab context.

        This ensures cookies, session tokens, same-origin protections, and
        reCAPTCHA tokens are correctly provided.
        """
        async with self._lock:
            await self.ensure_tab()

            # 1. Obtain reCAPTCHA token if action is specified (Fail-fast!)
            captcha_token = ""
            if captcha_action:
                captcha_token = await self.get_recaptcha_token(captcha_action)
                if not captcha_token:
                    raise RuntimeError(
                        f"Failed to obtain valid reCAPTCHA Enterprise token for action '{captcha_action}'. "
                        "Aborting Google Flow request to prevent 403 Forbidden rejection."
                    )

            # 2. Inject captcha token into clientContext
            if captcha_token:
                recaptcha_context = {
                    "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
                    "token": captcha_token,
                }
                if "clientContext" in body:
                    body["clientContext"]["recaptchaContext"] = recaptcha_context
                if "requests" in body and isinstance(body["requests"], list):
                    for req in body["requests"]:
                        if isinstance(req, dict) and "clientContext" in req:
                            req["clientContext"]["recaptchaContext"] = recaptcha_context

            # 3. Construct API execution script in page context
            url = f"https://aisandbox-pa.googleapis.com{endpoint}"
            headers: Dict[str, str] = {
                "Content-Type": "application/json",
                "x-goog-api-key": _get_flow_public_api_key(),
            }
            if not self._flow_key:
                self._flow_key = self._load_persisted_flow_key()
            if self._flow_key:
                headers["Authorization"] = f"Bearer {self._flow_key}"

            script = f"""(async () => {{
                // Hook to capture any Bearer token if sent by page
                const headers = {json.dumps(headers)};
                if (window.__FLOW_KEY__ && !headers['Authorization']) {{
                    headers['Authorization'] = `Bearer ${{window.__FLOW_KEY__}}`;
                }}

                const fetchOptions = {{
                    method: '{method}',
                    headers: headers,
                    credentials: 'include'
                }};

                if ('{method}' !== 'GET' && '{method}' !== 'HEAD') {{
                    fetchOptions.body = JSON.stringify({json.dumps(body)});
                }}

                try {{
                    const resp = await fetch('{url}', fetchOptions);
                    const status = resp.status;
                    let data = null;
                    const text = await resp.text();
                    try {{
                        data = JSON.parse(text);
                    }} catch (e) {{
                        data = {{ rawText: text }};
                    }}

                    return JSON.stringify({{
                        status: status,
                        data: data,
                        ok: resp.ok
                    }});
                }} catch (err) {{
                    return JSON.stringify({{
                        status: 0,
                        error: err.message
                    }});
                }}
            }})()"""

            raw_res = await self.evaluate(script, timeout=timeout)
            parsed = json.loads(raw_res) if isinstance(raw_res, str) else (raw_res or {})

            # Check if token is needed or expired (401)
            status = parsed.get("status", 0)
            if status == 401:
                logger.warning("Google Flow API returned 401 UNAUTHENTICATED. Checking page session...")
                self._flow_key = None

            return parsed
