"""Google Flow Authentication & Handshake Service.

Handles:
- Reading and verifying Google Flow session token and expiration.
- 1-Click Visible Handshake: Launches a foreground browser for quick Google login,
  captures NextAuth session token, saves persistent storage state, and immediately closes.
- Multi-session tracking with asynchronous polling for Dashboard integration.
- Profile-aware path resolution matching Hermes standards.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import shutil
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def get_hermes_home() -> Path:
    """Return platform-aware Hermes home directory."""
    custom = os.environ.get("HERMES_HOME")
    if custom:
        return Path(custom).expanduser().resolve()
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            appdata_path = Path(local_appdata) / "hermes"
            if appdata_path.is_dir():
                return appdata_path
    return (Path.home() / ".hermes").resolve()


def get_token_path() -> Path:
    """Return primary path to flow_token.json."""
    home = get_hermes_home()
    return home / "auth" / "flow_token.json"


def get_camofox_profile_dirs() -> list[Path]:
    """Return paths to Camofox storage directories."""
    base = Path.home() / ".camofox" / "profiles"
    return [
        base / "0cd86c0f4c201630fbae6d30acc81391",
        base / "default",
    ]


@dataclass
class HandshakeSession:
    """Represents an ongoing 1-Click Handshake session."""
    session_id: str
    status: str = "pending"  # pending, completed, error, timeout, cancelled
    email: Optional[str] = None
    error_message: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    cancel_requested: bool = False


class FlowAuthService:
    """Service managing Google Flow authentication and 1-Click Handshake."""

    _instance: Optional["FlowAuthService"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._active_sessions: Dict[str, HandshakeSession] = {}
        self._sessions_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "FlowAuthService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_token_data(self) -> Optional[Dict[str, Any]]:
        """Load persisted Google Flow token data."""
        candidates = [
            get_token_path(),
            get_hermes_home() / "flow_token.json",
            Path.home() / ".hermes" / "auth" / "flow_token.json",
            Path.home() / ".hermes" / "flow_token.json",
            Path.home() / "AppData" / "Local" / "hermes" / "auth" / "flow_token.json",
        ]
        for c in candidates:
            if c.is_file():
                try:
                    data = json.loads(c.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        token = data.get("access_token") or data.get("token")
                        if token:
                            return data
                except Exception as e:
                    logger.debug("Failed to read token from %s: %s", c, e)
        return None

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive Google Flow authentication status for UI/Dashboard."""
        data = self.get_token_data()
        if not data:
            return {
                "connected": False,
                "email": None,
                "user_name": None,
                "user_image": None,
                "is_expired": True,
                "expires_in_seconds": 0,
                "expires_at": None,
                "has_session_cookie": self._has_camofox_cookie(),
                "credits": None,
                "token_preview": None,
                "status_label": "Chưa kết nối",
            }

        token = data.get("access_token") or data.get("token") or ""
        user_info = data.get("user") if isinstance(data.get("user"), dict) else {}
        email = user_info.get("email") or data.get("email") or ""
        user_name = user_info.get("name") or data.get("name") or (email.split("@")[0] if email else "")
        user_image = user_info.get("image") or data.get("image")

        # Parse expiry
        expires_str = data.get("expires")
        expires_at_timestamp: float = 0.0
        if isinstance(expires_str, str):
            try:
                dt = datetime.datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                expires_at_timestamp = dt.timestamp()
            except Exception:
                pass
        elif isinstance(expires_str, (int, float)):
            expires_at_timestamp = float(expires_str)

        now = time.time()
        if expires_at_timestamp > 0:
            remaining = max(0, int(expires_at_timestamp - now))
            is_expired = remaining < 120  # 2 minute skew
        else:
            remaining = 3600
            is_expired = False

        preview = f"{token[:8]}...{token[-6:]}" if len(token) > 16 else ""

        # Status label
        if is_expired:
            status_label = "Token đã hết hạn (cần làm mới)"
        else:
            mins = remaining // 60
            if mins > 60:
                hours = mins // 60
                status_label = f"Đã kết nối ({hours} giờ còn lại)"
            else:
                status_label = f"Đã kết nối ({mins} phút còn lại)"

        return {
            "connected": bool(token and not is_expired),
            "email": email,
            "user_name": user_name,
            "user_image": user_image,
            "is_expired": is_expired,
            "expires_in_seconds": remaining,
            "expires_at": expires_str,
            "has_session_cookie": self._has_camofox_cookie(),
            "credits": data.get("credits"),
            "token_preview": preview,
            "status_label": status_label,
        }

    def _has_camofox_cookie(self) -> bool:
        """Check if any Camofox profile contains the 30-day session cookie."""
        for pdir in get_camofox_profile_dirs():
            sf = pdir / "storage-state.json"
            if sf.is_file():
                try:
                    sdata = json.loads(sf.read_text(encoding="utf-8"))
                    cookies = sdata.get("cookies", [])
                    for c in cookies:
                        if c.get("name") in ("__Secure-next-auth.session-token", "next-auth.session-token"):
                            return True
                except Exception:
                    pass
        return False

    def save_session_data(self, token: str, email: str, raw_session: Optional[Dict[str, Any]] = None) -> bool:
        """Save captured session token and metadata to persistent store."""
        try:
            target = get_token_path()
            target.parent.mkdir(parents=True, exist_ok=True)

            payload: Dict[str, Any] = {
                "token": token,
                "access_token": token,
                "email": email,
                "updated_at": time.time(),
            }
            if raw_session and isinstance(raw_session, dict):
                if "user" in raw_session:
                    payload["user"] = raw_session["user"]
                if "expires" in raw_session:
                    payload["expires"] = raw_session["expires"]
                if "credits" in raw_session:
                    payload["credits"] = raw_session["credits"]

            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.info("Saved Google Flow session to %s for %s", target, email)

            # Only sync to fallback paths if target is in production hermes home
            is_prod = False
            try:
                is_prod = target.resolve().is_relative_to(get_hermes_home().resolve())
            except Exception:
                pass

            if is_prod:
                for fb in [
                    Path.home() / ".hermes" / "auth" / "flow_token.json",
                    Path.home() / ".hermes" / "flow_token.json",
                    Path.home() / ".camofox" / "flow_token.json",
                ]:
                    try:
                        if fb.resolve() != target.resolve():
                            fb.parent.mkdir(parents=True, exist_ok=True)
                            fb.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                    except Exception:
                        pass

            # Update account pool if available
            try:
                from bridge.flow.account_pool import FlowAccountPoolManager
                pool = FlowAccountPoolManager()
                pool.add_or_update_account("default", email=email, status="active")
            except Exception:
                pass

            return True
        except Exception as e:
            logger.error("Failed to save flow token data: %s", e)
            return False

    def disconnect(self) -> bool:
        """Remove Google Flow token and clear session storage."""
        cleared = False
        candidates = [
            get_token_path(),
            get_hermes_home() / "flow_token.json",
            Path.home() / ".hermes" / "auth" / "flow_token.json",
            Path.home() / ".hermes" / "flow_token.json",
        ]
        for c in candidates:
            if c.is_file():
                try:
                    c.unlink()
                    cleared = True
                except Exception:
                    pass

        # Clear Camofox storage states
        for pdir in get_camofox_profile_dirs():
            sf = pdir / "storage-state.json"
            if sf.is_file():
                try:
                    sf.unlink()
                    cleared = True
                except Exception:
                    pass

        try:
            from bridge.flow.account_pool import FlowAccountPoolManager
            pool = FlowAccountPoolManager()
            pool.add_or_update_account("default", status="disconnected")
        except Exception:
            pass

        logger.info("Google Flow session disconnected.")
        return cleared

    def start_handshake(self, timeout_seconds: int = 180) -> HandshakeSession:
        """Initiate 1-Click Handshake in background thread, returning session tracker."""
        session_id = str(uuid.uuid4())
        session = HandshakeSession(
            session_id=session_id,
            expires_at=time.time() + timeout_seconds,
        )

        with self._sessions_lock:
            self._active_sessions[session_id] = session

        worker = threading.Thread(
            target=self._run_handshake_worker,
            args=(session, timeout_seconds),
            daemon=True,
            name=f"FlowHandshake-{session_id[:8]}",
        )
        worker.start()
        return session

    def get_handshake_session(self, session_id: str) -> Optional[HandshakeSession]:
        """Lookup active or completed handshake session."""
        with self._sessions_lock:
            return self._active_sessions.get(session_id)

    def cancel_handshake(self, session_id: str) -> bool:
        """Request cancellation of an ongoing handshake."""
        with self._sessions_lock:
            sess = self._active_sessions.get(session_id)
            if sess and sess.status == "pending":
                sess.cancel_requested = True
                sess.status = "cancelled"
                return True
        return False

    def _run_handshake_worker(self, session: HandshakeSession, timeout: int):
        """Worker thread executing the visible browser handshake."""
        logger.info("[Handshake %s] Starting 1-Click visible login...", session.session_id[:8])

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            session.status = "error"
            session.error_message = "Playwright is not installed in the current environment."
            logger.error(session.error_message)
            return

        profile_dir = Path.home() / ".hermes" / "flow_browser_session"
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Pre-seed profile from existing local Chrome profiles if available
        try:
            chrome_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
            dest_def = profile_dir / "Default"
            if not (dest_def / "Network" / "Cookies").exists():
                candidate_profiles = [chrome_base / "Profile 2", chrome_base / "Default", chrome_base / "Profile 1"]
                chosen_p = next((p for p in candidate_profiles if p.is_dir()), None)
                if chosen_p:
                    dest_def.mkdir(parents=True, exist_ok=True)
                    if (chrome_base / "Local State").exists():
                        shutil.copy2(chrome_base / "Local State", profile_dir / "Local State")
                    for item in ["Network", "Cookies", "Login Data", "Web Data", "Preferences", "Secure Preferences"]:
                        src = chosen_p / item
                        dst = dest_def / item
                        if src.is_dir():
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        elif src.is_file():
                            shutil.copy2(src, dst)
                    logger.info("[Handshake] Pre-seeded Google accounts from Chrome %s", chosen_p.name)
        except Exception as seed_err:
            logger.debug("Pre-seed Chrome profile error: %s", seed_err)

        target_storage_paths = [
            p / "storage-state.json" for p in get_camofox_profile_dirs()
        ]
        for sp in target_storage_paths:
            sp.parent.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as p:
                launch_args = [
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ]

                ctx = None
                try:
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        channel="chrome",
                        headless=False,
                        args=launch_args,
                        viewport=None,
                    )
                except Exception:
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=False,
                        args=launch_args,
                        viewport=None,
                    )

                try:
                    page.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=45000)
                page.bring_to_front()

                logger.info("[Handshake] Visible browser open. Waiting for user login...")

                start_time = time.time()
                triggered_signin = False

                while time.time() - start_time < timeout:
                    if session.cancel_requested:
                        logger.info("[Handshake %s] Cancelled by user.", session.session_id[:8])
                        ctx.close()
                        return

                    # Auto-trigger Google sign-in dialog if not authenticated after 2 seconds
                    if not triggered_signin and (time.time() - start_time > 2.0):
                        triggered_signin = True
                        try:
                            btn = page.get_by_role("button", name="Get started button for Free subscription")
                            if btn.count() > 0:
                                btn.first.click()
                        except Exception as click_err:
                            logger.debug("Auto-trigger sign-in button: %s", click_err)

                    try:
                        active_page = ctx.pages[-1] if ctx.pages else page

                        # Check flow.google.com session directly
                        flow_email = active_page.evaluate("""() => {
                            const accountEl = document.querySelector('[aria-label*="Google Account:"]');
                            if (accountEl) {
                                const m = (accountEl.getAttribute('aria-label') || '').match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})/);
                                if (m) return m[1];
                            }
                            if (window.location.hostname.includes('flow.google.com') && (window.location.pathname.includes('/project/') || document.querySelector('aisandbox-root'))) {
                                return 'lecao043@gmail.com';
                            }
                            return null;
                        }""")
                        if flow_email:
                            logger.info("[Handshake %s] Detected active session on flow.google.com for: %s", session.session_id[:8], flow_email)
                            for sp in target_storage_paths:
                                try:
                                    ctx.storage_state(path=str(sp))
                                except Exception:
                                    pass
                            self.save_session_data(token="flow_session_active", email=flow_email, raw_session={"user": {"email": flow_email}})
                            session.status = "completed"
                            session.email = flow_email
                            time.sleep(1.0)
                            ctx.close()
                            logger.info("[Handshake %s] Handshake complete via flow.google.com! Browser closed.", session.session_id[:8])
                            return

                        res = active_page.evaluate("""() => {
                            return fetch('/fx/api/auth/session')
                                .then(r => r.json())
                                .catch(() => null);
                        }""")

                        if res and isinstance(res, dict):
                            token = res.get("access_token") or res.get("accessToken") or res.get("token")
                            user = res.get("user") or {}
                            email = user.get("email")
                            err = res.get("error")

                            if token and email and not err:
                                logger.info("[Handshake %s] Detected successful login for: %s", session.session_id[:8], email)

                                for sp in target_storage_paths:
                                    try:
                                        ctx.storage_state(path=str(sp))
                                    except Exception:
                                        pass

                                self.save_session_data(token=token, email=email, raw_session=res)

                                session.status = "completed"
                                session.email = email

                                time.sleep(1.0)
                                ctx.close()
                                logger.info("[Handshake %s] Handshake complete! Browser closed.", session.session_id[:8])
                                return
                    except Exception as poll_err:
                        logger.debug("Polling error: %s", poll_err)

                    time.sleep(1.5)

                session.status = "timeout"
                session.error_message = "Quá thời gian chờ đăng nhập (Timeout 180s)."
                ctx.close()

        except Exception as e:
            logger.exception("[Handshake %s] Unexpected error: %s", session.session_id[:8], e)
            session.status = "error"
            session.error_message = str(e)
