"""Antigravity (OAuth Bridge) provider profile for Hermes Agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Guarantee bridge runtime discovery from ~/.hermes/ even if hermes-agent git repo is wiped / updated
try:
    from hermes_constants import get_hermes_home
    _h_home = get_hermes_home()
except Exception:
    _h_home = Path.home() / ".hermes"

for _sub in ("tools", ""):
    _p = str(_h_home / "bridge" / "antigravity" / _sub) if _sub else str(_h_home / "bridge" / "antigravity")
    if Path(_p).exists() and _p not in sys.path:
        sys.path.insert(0, _p)

from providers import register_provider
from providers.base import ProviderProfile


class AntigravityProfile(ProviderProfile):
    """Antigravity OAuth Bridge provider profile."""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        """Fetch live discovered models from Code Assist."""
        try:
            try:
                from tools.antigravity_bridge.models import ModelDiscoveryManager
            except ImportError:
                from bridge.models import ModelDiscoveryManager
            mgr = ModelDiscoveryManager()
            disc = mgr.get_discovered_models(force_refresh=False)
            if disc:
                return [m.id for m in disc]
        except Exception:
            pass
        return list(self.fallback_models or ())

    def build_extra_body(
        self, *, session_id: str | None = None, **context: Any
    ) -> dict[str, Any]:
        """Support reasoning/thinking config forwarding and auto-wake bridge daemon."""
        try:
            from tools.antigravity_bridge.server import ensure_antigravity_bridge_running
            ensure_antigravity_bridge_running()
        except Exception:
            pass
        reasoning_config = context.get("reasoning_config")
        if not reasoning_config:
            return {}
        return {"thinking_config": reasoning_config}


antigravity = AntigravityProfile(
    name="antigravity",
    aliases=("google-antigravity", "antigravity-oauth"),
    display_name="Google Antigravity (OAuth)",
    description="Google Gemini & Claude models via Antigravity OAuth local bridge",
    signup_url="https://antigravity.google",
    env_vars=(),
    base_url="http://127.0.0.1:8100/v1",
    auth_type="oauth_external",
    default_aux_model="gemini-3.7-flash",
    supports_vision=True,
    fallback_models=(
        "gemini-3.7-pro",
        "gemini-3.7-flash",
        "gemini-3.7-flash-agent",
        "gemini-2.0-pro-exp-02-05",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "claude-3-7-sonnet",
        "claude-sonnet-4-6",
        "claude-3-5-sonnet-v2",
        "claude-3-5-haiku",
    ),
)

register_provider(antigravity)

try:
    from .injector import patch_all
    patch_all()
except Exception as e:
    import logging
    logging.getLogger("hermes").warning(f"Antigravity injector failed: {e}")


def _self_heal_environment() -> None:
    """Self-Healing Persistence Guard:
    Automatically runs on Hermes startup. Ensures workspace tools and configs
    remain 100% synchronized and healthy across any Hermes git updates.
    """
    try:
        bridge_dir = _h_home / "bridge" / "antigravity"
        try:
            from hermes_constants import get_repo_root
            repo_root = get_repo_root()
        except Exception:
            repo_root = Path.cwd()
        if repo_root and (repo_root / "run_agent.py").is_file():
            ws_tools = repo_root / "tools" / "antigravity_bridge"
            src_bridge = bridge_dir / "tools" / "antigravity_bridge"
            if not ws_tools.exists() and src_bridge.is_dir():
                import shutil
                shutil.copytree(src_bridge, ws_tools)
    except Exception:
        pass


def _auto_start_bridge_daemon() -> None:
    """Silently auto-start local OAuth bridge daemon in a background thread if authenticated."""
    import threading
    def _starter():
        try:
            try:
                from tools.antigravity_bridge.server import ensure_antigravity_bridge_running
            except ImportError:
                from bridge.server import ensure_antigravity_bridge_running
            ensure_antigravity_bridge_running()
        except Exception:
            pass

    t = threading.Thread(target=_starter, daemon=True, name="antigravity-bridge-autostart")
    t.start()


_self_heal_environment()
_auto_start_bridge_daemon()


