"""Google Flow Headless Auto-Refresh Daemon.

Ensures that the Google Flow OAuth access token ('ya29...') is always fresh
without interrupting the user or requiring manual logins:
- Uses the 30-day NextAuth session cookie stored in Camofox / browser session.
- Runs silently in headless mode (no popups or windows).
- Automatically invoked before video/image generation jobs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from bridge.flow.flow_auth_service import FlowAuthService, get_camofox_profile_dirs, get_hermes_home

logger = logging.getLogger(__name__)


class FlowRefreshDaemon:
    """Headless token refresh engine for Google Flow."""

    _instance: Optional["FlowRefreshDaemon"] = None
    _refresh_lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "FlowRefreshDaemon":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def ensure_active_token(self, min_validity_seconds: int = 300) -> Tuple[bool, str]:
        """Ensure an active, non-expired Google Flow access token is available.

        Returns (is_active, token_or_error).
        """
        auth_service = FlowAuthService.get_instance()
        status = auth_service.get_status()

        token_data = auth_service.get_token_data() or {}
        current_token = token_data.get("access_token") or token_data.get("token") or ""

        # Check if current token is still valid
        if current_token and not status.get("is_expired"):
            remaining = status.get("expires_in_seconds", 0)
            if remaining > min_validity_seconds:
                return True, current_token

        # Token is missing, expired, or about to expire -> acquire lock and refresh
        async with self._refresh_lock:
            # Re-check inside lock
            status = auth_service.get_status()
            token_data = auth_service.get_token_data() or {}
            current_token = token_data.get("access_token") or token_data.get("token") or ""
            if current_token and not status.get("is_expired") and status.get("expires_in_seconds", 0) > min_validity_seconds:
                return True, current_token

            logger.info("Google Flow token expired or expiring soon. Starting headless auto-refresh...")
            success, result = await self._perform_headless_refresh()
            if success:
                logger.info("Google Flow token auto-refreshed successfully!")
                return True, result
            else:
                logger.warning("Headless refresh failed: %s", result)
                if current_token:
                    # Fallback to current token if we have nothing else
                    logger.warning("Falling back to current token despite expiration warning.")
                    return True, current_token
                return False, result

    async def _perform_headless_refresh(self) -> Tuple[bool, str]:
        """Execute headless refresh using Camofox Bridge or Playwright."""
        # Try Method 1: Camofox Bridge Server (if running on 127.0.0.1:9377)
        try:
            try:
                from bridge.flow.camofox_bridge import CamofoxFlowBridge
            except ImportError:
                from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
            bridge = CamofoxFlowBridge()
            if bridge.is_server_running():
                tab_id = await bridge.ensure_tab()
                if tab_id:
                    script = """(() => {
                        return fetch('/fx/api/auth/session')
                            .then(r => r.json())
                            .then(d => JSON.stringify(d))
                            .catch(e => JSON.stringify({ error: e.message }));
                    })()"""
                    res = await bridge.evaluate(script)
                    if isinstance(res, str):
                        try:
                            res = json.loads(res)
                        except Exception:
                            pass
                    if isinstance(res, dict):
                        token = res.get("access_token") or res.get("accessToken") or res.get("token")
                        email = res.get("user", {}).get("email") or ""
                        err = res.get("error")
                        if token and not err:
                            FlowAuthService.get_instance().save_session_data(token, email, res)
                            return True, token
                        elif err:
                            logger.warning("Camofox session returned error: %s", err)
        except Exception as e:
            logger.debug("Camofox bridge headless refresh error: %s", e)

        # Try Method 2: Playwright Headless Context directly
        def _playwright_headless() -> Tuple[bool, str]:
            try:
                from playwright.sync_api import sync_playwright
                profile_dir = Path.home() / ".hermes" / "flow_browser_session"
                if not profile_dir.is_dir():
                    return False, "No browser session profile found. Please connect via 1-Click Handshake."

                target_storage_paths = [
                    p / "storage-state.json" for p in get_camofox_profile_dirs()
                ]

                with sync_playwright() as p:
                    try:
                        ctx = p.chromium.launch_persistent_context(
                            user_data_dir=str(profile_dir),
                            channel="chrome",
                            headless=True,
                            args=["--disable-blink-features=AutomationControlled"],
                        )
                    except Exception:
                        ctx = p.chromium.launch_persistent_context(
                            user_data_dir=str(profile_dir),
                            headless=True,
                            args=["--disable-blink-features=AutomationControlled"],
                        )
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    
                    # Direct fetch from labs.google auth session endpoint
                    try:
                        resp = page.goto("https://labs.google/fx/api/auth/session", timeout=45000)
                        if resp and resp.status == 200:
                            body_text = page.inner_text("body")
                            res = json.loads(body_text)
                            token = res.get("access_token") or res.get("accessToken") or res.get("token")
                            email = res.get("user", {}).get("email") or ""
                            err = res.get("error")
                            if token and not err and (token.startswith("ya29.") or len(token) > 40) and not token.startswith("flow_session"):
                                for sp in target_storage_paths:
                                    try:
                                        ctx.storage_state(path=str(sp))
                                    except Exception:
                                        pass
                                FlowAuthService.get_instance().save_session_data(token, email, res)
                                ctx.close()
                                return True, token
                    except Exception as direct_err:
                        logger.debug("Direct session navigation error: %s", direct_err)

                    # Fallback: navigate to flow tools and poll
                    page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=45000)

                    # Poll for session with short timeout
                    for _ in range(10):
                        try:
                            res = page.evaluate("""() => {
                                return fetch('/fx/api/auth/session')
                                    .then(r => r.json())
                                    .catch(() => null);
                            }""")
                            if res and isinstance(res, dict):
                                token = res.get("access_token") or res.get("accessToken") or res.get("token")
                                email = res.get("user", {}).get("email") or ""
                                err = res.get("error")
                                if token and not err and (token.startswith("ya29.") or len(token) > 40) and not token.startswith("flow_session"):
                                    # Sync storage state
                                    for sp in target_storage_paths:
                                        try:
                                            ctx.storage_state(path=str(sp))
                                        except Exception:
                                            pass

                                    FlowAuthService.get_instance().save_session_data(token, email, res)
                                    ctx.close()
                                    return True, token
                        except Exception:
                            pass
                        time.sleep(1.0)

                    ctx.close()
                    return False, "Session cookie expired on server. Please reconnect via 1-Click Handshake."
            except Exception as exc:
                return False, f"Playwright headless refresh error: {exc}"

        return await asyncio.to_thread(_playwright_headless)


async def ensure_flow_token() -> Tuple[bool, str]:
    """Helper function to guarantee an active Google Flow token."""
    return await FlowRefreshDaemon.get_instance().ensure_active_token()
