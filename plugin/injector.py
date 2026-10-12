"""Antigravity & Google Flow Runtime Dashboard Injector for Hermes Agent.

Provides robust, non-invasive runtime monkey-patching of the Hermes Web Dashboard
(hermes_cli.web_server) to inject:
1. Google Antigravity (OAuth) management card.
2. Google Flow (Media & VideoFX) Camofox browser management card.

Design Principles:
- Zero Core Modifications: Never touch hermes-agent git files.
- Dynamic Polling: Replaces fragile sleep timers with adaptive module polling.
- Strictly Idempotent: Can be invoked repeatedly (e.g. plugin reload) without
  duplicating entries or stacking recursive wrapper layers.
- Signature Preservation: Uses functools.wraps to maintain exact FastAPI
  type annotations and dependency injection behavior.
- Self-Healing & Diagnostics: Exposes get_injection_health() for automated checks.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import secrets
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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

logger = logging.getLogger("hermes.plugins.antigravity.injector")

# Marker attribute to guarantee idempotency across reload cycles
PATCH_MARKER = "__antigravity_patched__"

# Thread control
_injector_thread: Optional[threading.Thread] = None
_injector_lock = threading.Lock()


# =============================================================================
# Diagnostic Health State
# =============================================================================

_HEALTH_STATE: Dict[str, Any] = {
    "web_server_detected": False,
    "catalog_patched": False,
    "model_options_patched": False,
    "start_route_patched": False,
    "submit_route_patched": False,
    "delete_route_patched": False,
    "cli_auth_patched": False,
    "last_patch_time": None,
    "error": None,
}


def get_injection_health() -> Dict[str, Any]:
    """Return diagnostic snapshot of the runtime injection state."""
    state = dict(_HEALTH_STATE)
    state["is_healthy"] = (
        state["web_server_detected"]
        and state["catalog_patched"]
        and state["start_route_patched"]
    )
    return state


# =============================================================================
# Lifecycle & Polling Wait
# =============================================================================

def _wait_for_web_server(timeout: float = 15.0) -> bool:
    """Adaptively poll for hermes_cli.web_server without magic fixed sleeps.

    Checks every 50ms up to timeout. Handles slow startup, containerized runs,
    and heavy CPU load gracefully.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if (
            "hermes_cli.web_server" in sys.modules
            or "hermes_cli.web_routers.oauth" in sys.modules
        ):
            return True
        time.sleep(0.05)
    return False


def _run_patches():
    """Background entry point for applying patches."""
    if _wait_for_web_server(timeout=15.0):
        try:
            patch_dashboard_ui()
        except Exception as e:
            _HEALTH_STATE["error"] = str(e)
            logger.warning(f"Failed to patch dashboard UI: {e}", exc_info=True)

    try:
        patch_cli_auth()
    except Exception as e:
        logger.warning(f"Failed to patch CLI auth: {e}")


def patch_all(force: bool = False):
    """Apply runtime monkey-patches to inject Antigravity UI into Hermes Core safely.

    Idempotent: Only spawns one active watcher thread unless force=True.
    """
    global _injector_thread

    # Synchronous patches needed immediately by CLI & Gateway (Telegram, Discord, etc.)
    try:
        patch_cli_auth()
    except Exception as e:
        logger.warning(f"Failed to patch CLI auth: {e}")

    try:
        patch_models_catalog()
    except Exception as e:
        logger.warning(f"Failed to patch models catalog: {e}")

    try:
        patch_image_generation()
    except Exception as e:
        logger.warning(f"Failed to patch image generation: {e}")

    with _injector_lock:
        if _injector_thread is not None and _injector_thread.is_alive() and not force:
            return
        _injector_thread = threading.Thread(
            target=_run_patches, daemon=True, name="antigravity-injector"
        )
        _injector_thread.start()


# =============================================================================
# Dashboard UI Patching
# =============================================================================


def _inject_antigravity_into_model_options(payload: Any) -> None:
    """Inject Google Antigravity provider and dynamic models into dashboard model options."""
    if not isinstance(payload, dict):
        return
    providers = payload.setdefault("providers", [])
    if not isinstance(providers, list):
        return

    # Don't duplicate
    for p in providers:
        if isinstance(p, dict) and p.get("slug") == "antigravity":
            return

    auth_status = get_antigravity_auth_status()
    is_authed = bool(auth_status.get("logged_in"))

    model_ids = []
    try:
        try:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
        except ImportError:
            try:
                from bridge.models import ModelDiscoveryManager
            except ImportError:
                ModelDiscoveryManager = None
        if ModelDiscoveryManager:
            mgr = ModelDiscoveryManager()
            disc = mgr.get_discovered_models(force_refresh=False)
            model_ids = [m.id for m in disc]
    except Exception as e:
        logger.debug(f"Model discovery for dashboard injection failed: {e}")

    if not model_ids:
        model_ids = [
            "gemini-3.7-flash-tiered",
            "claude-sonnet-4-6",
            "claude-opus-4-6-thinking",
            "gemini-3.6-flash-high",
            "gemini-3.6-flash-medium",
            "gemini-3.1-pro-high",
            "gpt-oss-120b-medium",
        ]

    current_provider = str(payload.get("provider") or "").lower()
    is_current = (current_provider == "antigravity")

    antigravity_row = {
        "slug": "antigravity",
        "name": "Google Antigravity (Code Assist)",
        "is_current": is_current,
        "is_user_defined": False,
        "models": model_ids,
        "total_models": len(model_ids),
        "source": "antigravity-bridge",
        "authenticated": is_authed,
        "auth_type": "oauth",
        "base_url": "http://127.0.0.1:8100/v1",
        "description": "Gemini 3.7, Claude Sonnet 4.6, Claude Opus 4.6 & GPT-OSS via Google Antigravity OAuth",
        "featured_models": [
            "gemini-3.7-flash-tiered",
            "claude-sonnet-4-6",
            "claude-opus-4-6-thinking",
            "gemini-3.6-flash-high",
            "gpt-oss-120b-medium",
        ],
    }

    providers.insert(0, antigravity_row)

def _auto_start_bridge_daemon() -> None:
    """Silently ensure local OAuth bridge daemon is running in a background thread."""
    import threading
    def _worker():
        try:
            try:
                from tools.antigravity_bridge.server import ensure_antigravity_bridge_running
            except ImportError:
                from bridge.server import ensure_antigravity_bridge_running
            ensure_antigravity_bridge_running()
        except Exception:
            pass
    t = threading.Thread(target=_worker, daemon=True, name="antigravity-bridge-autostart")
    t.start()


def patch_dashboard_ui():
    """Patch the web server catalog and routes idempotently."""
    if "hermes_cli.web_server" not in sys.modules:
        return

    # Auto-wake bridge server daemon in background if authenticated
    _auto_start_bridge_daemon()

    import hermes_cli.web_server as ws

    _HEALTH_STATE["web_server_detected"] = True

    # 1. Patch Catalog Builder
    original_build = getattr(ws, "_build_oauth_catalog", None)
    if original_build:
        if getattr(original_build, PATCH_MARKER, False):
            _HEALTH_STATE["catalog_patched"] = True
        else:
            @functools.wraps(original_build)
            def patched_build_oauth_catalog(*args, **kwargs):
                rows = original_build(*args, **kwargs)
                # Remove any existing entries for antigravity or google_flow to override with our custom status_fn
                rows = [r for r in rows if r.get("id") not in ("google_flow", "google-flow", "antigravity")]
                existing_ids = {r.get("id") for r in rows}

                # 1. Antigravity IDE OAuth card
                rows.insert(0, {
                    "id": "antigravity",
                    "name": "Google Antigravity (OAuth)",
                    "flow": "device_code",
                    "cli_command": "python manage.py login",
                    "docs_url": "https://antigravity.google",
                    "status_fn": get_antigravity_auth_status,
                })
                existing_ids.add("antigravity")

                # 2. Google Flow Media card (One-click Camofox login)
                rows.insert(1, {
                    "id": "google-flow",
                    "name": "Google Flow (Media & VideoFX)",
                    "flow": "device_code",
                    "cli_command": "python manage.py flow-login",
                    "docs_url": "https://labs.google/fx/tools/flow",
                    "status_fn": get_google_flow_auth_status,
                })
                existing_ids.add("google-flow")

                return rows

            setattr(patched_build_oauth_catalog, PATCH_MARKER, True)
            ws._build_oauth_catalog = patched_build_oauth_catalog
            _HEALTH_STATE["catalog_patched"] = True

    # 1b. Patch _resolve_provider_status so status is always intercepted regardless of upstream code
    orig_resolve = getattr(ws, "_resolve_provider_status", None)
    if orig_resolve and not getattr(orig_resolve, PATCH_MARKER, False):
        @functools.wraps(orig_resolve)
        def patched_resolve(provider_id: str, status_fn=None):
            if provider_id == "antigravity":
                return get_antigravity_auth_status()
            if provider_id in ("google-flow", "google_flow", "flow"):
                return get_google_flow_auth_status()
            return orig_resolve(provider_id, status_fn)

        setattr(patched_resolve, PATCH_MARKER, True)
        ws._resolve_provider_status = patched_resolve

    # 2. Ensure catalog tuples are present in _OAUTH_PROVIDER_CATALOG
    if hasattr(ws, "_OAUTH_PROVIDER_CATALOG"):
        current = list(ws._OAUTH_PROVIDER_CATALOG)
        current = [p for p in current if p.get("id") not in ("google_flow", "google-flow", "antigravity")]
        to_add = [
            {
                "id": "antigravity",
                "name": "Google Antigravity (OAuth)",
                "flow": "device_code",
                "cli_command": "python manage.py login",
                "docs_url": "https://antigravity.google",
                "status_fn": get_antigravity_auth_status,
            },
            {
                "id": "google-flow",
                "name": "Google Flow (Media & VideoFX)",
                "flow": "device_code",
                "cli_command": "python manage.py flow-login",
                "docs_url": "https://labs.google/fx/tools/flow",
                "status_fn": get_google_flow_auth_status,
            },
        ]
        ws._OAUTH_PROVIDER_CATALOG = tuple(to_add) + tuple(current)

    # 3. Patch device code start helper
    orig_start_helper = getattr(ws, "_start_device_code_flow", None)
    if orig_start_helper and not getattr(orig_start_helper, PATCH_MARKER, False):
        @functools.wraps(orig_start_helper)
        async def patched_start_device_code(provider_id: str, profile: Optional[str] = None, *args, **kwargs):
            if provider_id == "antigravity":
                return _dashboard_start_pkce(profile)
            if provider_id in ("google-flow", "google_flow", "flow"):
                return await _dashboard_start_flow(profile)
            return await orig_start_helper(provider_id, profile, *args, **kwargs)

        setattr(patched_start_device_code, PATCH_MARKER, True)
        ws._start_device_code_flow = patched_start_device_code

    # 4. Patch FastAPI Route Endpoints with functools.wraps
    try:
        app = ws.app
        _require_token = ws._require_token

        for route in app.routes:
            path = getattr(route, "path", None)
            endpoint = getattr(route, "endpoint", None)
            if not endpoint:
                continue

                        # Route: GET /api/model/options
            if path == "/api/model/options":
                if getattr(endpoint, PATCH_MARKER, False):
                    _HEALTH_STATE["model_options_patched"] = True
                else:
                    @functools.wraps(endpoint)
                    async def patched_model_options(*args, **kwargs):
                        res = await endpoint(*args, **kwargs)
                        _inject_antigravity_into_model_options(res)
                        return res

                    setattr(patched_model_options, PATCH_MARKER, True)
                    route.endpoint = patched_model_options
                    _HEALTH_STATE["model_options_patched"] = True

            # Route: POST /start
            if path == "/api/providers/oauth/{provider_id}/start":
                if getattr(endpoint, PATCH_MARKER, False):
                    _HEALTH_STATE["start_route_patched"] = True
                else:
                    @functools.wraps(endpoint)
                    async def patched_start_endpoint(*args, **kwargs):
                        provider_id = kwargs.get("provider_id")
                        if provider_id == "google-flow":
                            request = kwargs.get("request")
                            if request:
                                _require_token(request)
                            return await _dashboard_start_flow(kwargs.get("profile"))
                        if provider_id == "antigravity":
                            request = kwargs.get("request")
                            if request:
                                _require_token(request)
                            return _dashboard_start_pkce(kwargs.get("profile"))
                        return await endpoint(*args, **kwargs)

                    setattr(patched_start_endpoint, PATCH_MARKER, True)
                    route.endpoint = patched_start_endpoint
                    _HEALTH_STATE["start_route_patched"] = True

            # Route: POST /submit
            elif path == "/api/providers/oauth/{provider_id}/submit":
                if getattr(endpoint, PATCH_MARKER, False):
                    _HEALTH_STATE["submit_route_patched"] = True
                else:
                    @functools.wraps(endpoint)
                    async def patched_submit_endpoint(*args, **kwargs):
                        provider_id = kwargs.get("provider_id")
                        if provider_id == "antigravity":
                            request = kwargs.get("request")
                            if request:
                                _require_token(request)
                            body = kwargs.get("body")
                            profile = kwargs.get("profile")
                            loop = asyncio.get_running_loop()
                            return await loop.run_in_executor(
                                None, _dashboard_submit_pkce, body.session_id, body.code, profile
                            )
                        return await endpoint(*args, **kwargs)

                    setattr(patched_submit_endpoint, PATCH_MARKER, True)
                    route.endpoint = patched_submit_endpoint
                    _HEALTH_STATE["submit_route_patched"] = True

            # Route: DELETE /{provider_id}
            elif path == "/api/providers/oauth/{provider_id}":
                if getattr(endpoint, PATCH_MARKER, False):
                    _HEALTH_STATE["delete_route_patched"] = True
                else:
                    @functools.wraps(endpoint)
                    async def patched_delete_endpoint(*args, **kwargs):
                        provider_id = kwargs.get("provider_id")
                        if provider_id in ("google-flow", "google_flow", "flow"):
                            request = kwargs.get("request")
                            if request:
                                _require_token(request)
                            return await _dashboard_disconnect_flow()
                        return await endpoint(*args, **kwargs)

                    setattr(patched_delete_endpoint, PATCH_MARKER, True)
                    route.endpoint = patched_delete_endpoint
                    _HEALTH_STATE["delete_route_patched"] = True

        # Route: GET /flow-helper
        existing_paths = {getattr(r, "path", None) for r in app.routes}
        if "/flow-helper" not in existing_paths:
            from starlette.responses import HTMLResponse
            @app.get("/flow-helper", response_class=HTMLResponse)
            async def get_flow_helper():
                return HTMLResponse(_FLOW_HELPER_HTML)
        
        # 5. Patch hermes_cli.inventory.build_model_options_payload if loaded
        try:
            import hermes_cli.inventory as inv
            orig_bmop = getattr(inv, "build_model_options_payload", None)
            if orig_bmop and not getattr(orig_bmop, PATCH_MARKER, False):
                @functools.wraps(orig_bmop)
                def patched_bmop(*args, **kwargs):
                    res = orig_bmop(*args, **kwargs)
                    _inject_antigravity_into_model_options(res)
                    return res

                setattr(patched_bmop, PATCH_MARKER, True)
                inv.build_model_options_payload = patched_bmop
        except Exception as ex:
            logger.debug(f"inventory patch skipped: {ex}")

        # 6. Patch model assignment to ensure antigravity sets default base_url & api_key
        orig_apply_assignment = getattr(ws, "_apply_model_assignment_sync", None)
        if orig_apply_assignment and not getattr(orig_apply_assignment, PATCH_MARKER, False):
            @functools.wraps(orig_apply_assignment)
            def patched_apply_model_assignment(scope, provider, model, task, base_url, api_key=""):
                if str(provider).strip().lower() == "antigravity":
                    if not base_url:
                        base_url = "http://127.0.0.1:8100/v1"
                    if not api_key:
                        api_key = "antigravity"
                    _auto_start_bridge_daemon()
                return orig_apply_assignment(scope, provider, model, task, base_url, api_key)

            setattr(patched_apply_model_assignment, PATCH_MARKER, True)
            ws._apply_model_assignment_sync = patched_apply_model_assignment

        _HEALTH_STATE["last_patch_time"] = time.time()
        logger.info("Antigravity & Google Flow dashboard hooks successfully injected.")
    except Exception as e:
        _HEALTH_STATE["error"] = str(e)
        logger.warning(f"Failed to patch FastAPI routes: {e}")


# =============================================================================
# CLI Auth Patching
# =============================================================================

def patch_cli_auth():
    """Patch hermes_cli auth registry and status lookup idempotently."""
    try:
        import hermes_cli.auth_commands as ac
        if hasattr(ac, "_OAUTH_CAPABLE_PROVIDERS"):
            caps = getattr(ac, "_OAUTH_CAPABLE_PROVIDERS")
            if isinstance(caps, set):
                caps.add("antigravity")
                caps.add("google-flow")
    except Exception:
        pass

    try:
        import hermes_cli.auth as ha
        # Register antigravity in PROVIDER_REGISTRY so resolve_runtime_provider recognises it
        if hasattr(ha, "PROVIDER_REGISTRY") and "antigravity" not in ha.PROVIDER_REGISTRY:
            try:
                from hermes_cli.auth import ProviderConfig
                ha.PROVIDER_REGISTRY["antigravity"] = ProviderConfig(
                    id="antigravity",
                    name="Google Antigravity (OAuth)",
                    auth_type="oauth_external",
                    portal_base_url="",
                    inference_base_url="http://127.0.0.1:8100/v1",
                    client_id="",
                    scope="",
                    extra={},
                    api_key_env_vars=(),
                    base_url_env_var="",
                )
            except Exception as e:
                logger.debug("Failed to register antigravity in PROVIDER_REGISTRY: %s", e)

        orig_get_status = getattr(ha, "get_auth_status", None)
        if orig_get_status:
            if getattr(orig_get_status, PATCH_MARKER, False):
                _HEALTH_STATE["cli_auth_patched"] = True
            else:
                @functools.wraps(orig_get_status)
                def patched_get_auth_status(provider: str, *args, **kwargs):
                    if provider == "antigravity":
                        return get_antigravity_auth_status()
                    if provider == "google-flow":
                        return get_google_flow_auth_status()
                    return orig_get_status(provider, *args, **kwargs)

                setattr(patched_get_auth_status, PATCH_MARKER, True)
                ha.get_auth_status = patched_get_auth_status
                _HEALTH_STATE["cli_auth_patched"] = True

        ha.get_antigravity_auth_status = get_antigravity_auth_status
        ha.get_google_flow_auth_status = get_google_flow_auth_status

        # Patch hermes_cli.runtime_provider.resolve_runtime_provider for antigravity
        try:
            import hermes_cli.runtime_provider as hrp
            orig_resolve_rp = getattr(hrp, "resolve_runtime_provider", None)
            if orig_resolve_rp and not getattr(orig_resolve_rp, PATCH_MARKER, False):
                @functools.wraps(orig_resolve_rp)
                def patched_resolve_runtime_provider(*args, **kwargs):
                    req = kwargs.get("requested")
                    if not req:
                        try:
                            mcfg = hrp._get_model_config()
                            req = mcfg.get("provider") if isinstance(mcfg, dict) else None
                        except Exception:
                            req = None
                    req_norm = (req or "").strip().lower()
                    if req_norm in ("antigravity", "google-antigravity", "antigravity-oauth"):
                        try:
                            try:
                                from tools.antigravity_bridge.server import ensure_antigravity_bridge_running
                            except ImportError:
                                from bridge.server import ensure_antigravity_bridge_running
                            ensure_antigravity_bridge_running()
                        except Exception:
                            pass
                        return {
                            "provider": "antigravity",
                            "api_mode": "chat_completions",
                            "base_url": "http://127.0.0.1:8100/v1",
                            "api_key": "antigravity-local-token",
                            "source": "antigravity-oauth",
                            "requested_provider": req,
                        }
                    return orig_resolve_rp(*args, **kwargs)

                setattr(patched_resolve_runtime_provider, PATCH_MARKER, True)
                hrp.resolve_runtime_provider = patched_resolve_runtime_provider
        except Exception as e:
            logger.debug("Failed to patch hermes_cli.runtime_provider: %s", e)
    except Exception as e:
        logger.debug("Failed to patch hermes_cli.auth: %s", e)


# =============================================================================
# Models Catalog & Dynamic Discovery Patching (CLI, Gateway, Telegram, Discord)
# =============================================================================

def patch_models_catalog():
    """Hook hermes_cli.models and CANONICAL_PROVIDERS for dynamic model discovery across all interfaces."""
    import sys
    try:
        import hermes_cli.models as hm

        # 1. Patch provider_model_ids for antigravity
        orig_pmi = getattr(hm, "provider_model_ids", None)
        if orig_pmi and not getattr(orig_pmi, PATCH_MARKER, False):
            @functools.wraps(orig_pmi)
            def patched_provider_model_ids(provider: Optional[str], *, force_refresh: bool = False) -> list[str]:
                norm = str(provider or "").strip().lower()
                if norm in {"antigravity", "google-antigravity", "antigravity-oauth"}:
                    try:
                        try:
                            from tools.antigravity_bridge.models import ModelDiscoveryManager
                        except ImportError:
                            from bridge.models import ModelDiscoveryManager
                        mgr = ModelDiscoveryManager()
                        disc = mgr.get_discovered_models(force_refresh=force_refresh)
                        if disc:
                            return [m.id for m in disc]
                    except Exception as exc:
                        logger.debug("Antigravity dynamic discovery failed: %s", exc)
                return orig_pmi(provider, force_refresh=force_refresh)

            setattr(patched_provider_model_ids, PATCH_MARKER, True)
            hm.provider_model_ids = patched_provider_model_ids

        # 1b. Patch cached_provider_model_ids for antigravity
        orig_cpmi = getattr(hm, "cached_provider_model_ids", None)
        if orig_cpmi and not getattr(orig_cpmi, PATCH_MARKER, False):
            @functools.wraps(orig_cpmi)
            def patched_cached_provider_model_ids(provider: Optional[str], *, force_refresh: bool = False, **kwargs) -> list[str]:
                norm = str(provider or "").strip().lower()
                if norm in {"antigravity", "google-antigravity", "antigravity-oauth"}:
                    try:
                        try:
                            from tools.antigravity_bridge.models import ModelDiscoveryManager
                        except ImportError:
                            from bridge.models import ModelDiscoveryManager
                        mgr = ModelDiscoveryManager()
                        disc = mgr.get_discovered_models(force_refresh=force_refresh)
                        if disc:
                            return [m.id for m in disc]
                    except Exception as exc:
                        logger.debug("Antigravity cached dynamic discovery failed: %s", exc)
                return orig_cpmi(provider, force_refresh=force_refresh, **kwargs)

            setattr(patched_cached_provider_model_ids, PATCH_MARKER, True)
            hm.cached_provider_model_ids = patched_cached_provider_model_ids

        # 2. Add to CANONICAL_PROVIDERS if missing (ensures /model surfaces it)
        if hasattr(hm, "CANONICAL_PROVIDERS"):
            if not any(p.slug == "antigravity" for p in hm.CANONICAL_PROVIDERS):
                try:
                    from hermes_cli.models import ProviderEntry
                    hm.CANONICAL_PROVIDERS.append(
                        ProviderEntry(
                            "antigravity",
                            "Google Antigravity (OAuth)",
                            "Google Gemini & Claude models via Antigravity OAuth local bridge",
                        )
                    )
                except Exception:
                    pass

        # 3. Clear stale provider_models_cache disk entry for antigravity
        try:
            hm.clear_provider_models_cache("antigravity")
        except Exception:
            pass

        # 4. Pre-populate _PROVIDER_MODELS['antigravity'] with discovered models
        try:
            try:
                from tools.antigravity_bridge.models import ModelDiscoveryManager
            except ImportError:
                from bridge.models import ModelDiscoveryManager
            mgr = ModelDiscoveryManager()
            disc = mgr.get_discovered_models(force_refresh=False)
            if disc:
                hm._PROVIDER_MODELS["antigravity"] = [m.id for m in disc]
        except Exception:
            pass

    except Exception as e:
        logger.debug("patch_models_catalog failed: %s", e)


def patch_image_generation():
    """Ensure AntigravityImageGenProvider is eagerly registered in agent.image_gen_registry."""
    try:
        from agent.image_gen_registry import register_provider
        from hermes_constants import hermes_home_key

        try:
            from plugins.image_gen.antigravity import AntigravityImageGenProvider
        except ImportError:
            try:
                from image_gen.antigravity import AntigravityImageGenProvider
            except ImportError:
                return

        provider = AntigravityImageGenProvider()
        register_provider(provider)
        try:
            register_provider(provider, scope=hermes_home_key())
        except Exception:
            pass
        logger.debug("Antigravity image_gen provider registered via injector")
    except Exception as e:
        logger.debug("Failed to patch image generation: %e", e)


# =============================================================================
# Authentication Status & Health Checks
# =============================================================================

def get_antigravity_auth_status() -> Dict[str, Any]:
    """Check Antigravity IDE OAuth credential health."""
    try:
        try:
            from tools.antigravity_bridge.auth import AntigravityAuthManager
        except ImportError:
            from bridge.auth import AntigravityAuthManager

        mgr = AntigravityAuthManager()
        creds = mgr.load_stored_credentials()
        if creds:
            import datetime
            is_valid = bool(not creds.is_expired or creds.refresh_token)
            exp_iso = None
            if creds.expires_at:
                try:
                    exp_iso = datetime.datetime.fromtimestamp(creds.expires_at).isoformat()
                except Exception:
                    pass

            quota_badge = ""
            if creds.email:
                try:
                    try:
                        from tools.antigravity_bridge.models import ModelDiscoveryManager
                    except ImportError:
                        from bridge.models import ModelDiscoveryManager
                    dmgr = ModelDiscoveryManager()
                    cache = dmgr._load_cache_from_disk()
                    if cache and cache.get("models"):
                        claude_quota = cache["models"].get("claude-sonnet-4-6", {}).get("quotaInfo", {}).get("remainingFraction")
                        if claude_quota is not None:
                            quota_badge = f" | Claude: {int(claude_quota * 100)}%"
                except Exception:
                    pass

            label = f"{creds.email}{quota_badge}" if creds.email else "Google Antigravity OAuth"

            return {
                "logged_in": is_valid,
                "provider": "antigravity",
                "source": "antigravity_oauth",
                "source_label": label,
                "access_token": creds.access_token,
                "expires_at": exp_iso,
                "has_refresh_token": bool(creds.refresh_token),
            }
    except Exception as e:
        logger.debug("get_antigravity_auth_status error: %s", e)

    return {
        "logged_in": False,
        "provider": "antigravity",
        "source": "antigravity_oauth",
        "source_label": "Google Antigravity OAuth",
    }


def get_google_flow_auth_status() -> Dict[str, Any]:
    """Lightweight, non-blocking check for Google Flow Camofox session."""
    try:
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        try:
            from bridge.flow.account_pool import FlowAccountPoolManager
        except ImportError:
            FlowAccountPoolManager = None

    if FlowAccountPoolManager:
        try:
            mgr = FlowAccountPoolManager()
            acc = mgr.get_active_account()
            if acc and acc.status == "active":
                email_str = acc.email or "Google Flow Account"
                label_str = f" ({acc.label})" if acc.label else ""
                return {
                    "logged_in": True,
                    "source": "camofox",
                    "source_label": f"{email_str}{label_str}",
                    "token_preview": acc.id,
                    "has_refresh_token": True,
                }
        except Exception:
            pass

    return {
        "logged_in": False,
        "source": "camofox",
        "source_label": "Not Signed In",
    }


_FLOW_HELPER_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google Flow - Hướng dẫn đăng nhập</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 24px;
      background-color: #0b0f12;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: #131b20;
      border: 1px solid #1e293b;
      border-radius: 16px;
      padding: 40px 32px;
      max-width: 520px;
      width: 100%;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
      text-align: center;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #065f46;
      color: #34d399;
      font-size: 13px;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 9999px;
      margin-bottom: 20px;
    }
    h1 {
      font-size: 22px;
      margin: 0 0 14px;
      color: #f8fafc;
      font-weight: 700;
    }
    p {
      font-size: 15px;
      line-height: 1.6;
      color: #94a3b8;
      margin: 0 0 24px;
    }
    .highlight {
      color: #fbbf24;
      font-weight: 600;
    }
    .steps {
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 18px 20px;
      text-align: left;
      margin-bottom: 24px;
    }
    .steps ol {
      margin: 0;
      padding-left: 20px;
      color: #cbd5e1;
      font-size: 14px;
      line-height: 1.9;
    }
    .footer {
      font-size: 13px;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">🦊 Camofox Desktop Đang Hoạt Động</div>
    <h1>Cửa sổ Camofox đã mở trên màn hình!</h1>
    <p>Google Flow yêu cầu xác thực bảo mật nên <span class="highlight">cần đăng nhập trực tiếp trên cửa sổ trình duyệt Camofox Desktop</span> vừa xuất hiện trên máy tính của bạn.</p>
    <div class="steps">
      <ol>
        <li>Nhấn vào cửa sổ trình duyệt <b>Camofox</b> trên thanh tác vụ (Taskbar).</li>
        <li>Đăng nhập tài khoản Google của bạn tại đó.</li>
        <li>Sau khi đăng nhập xong, bạn có thể đóng tab này lại.</li>
      </ol>
    </div>
    <div class="footer">
      ⚡ Hermes Dashboard đang tự động lắng nghe và sẽ hiển thị <b>Connected</b> ngay khi bạn đăng nhập xong!
    </div>
  </div>
</body>
</html>
"""


# =============================================================================
# Dashboard Flow Login & Disconnect Implementations
# =============================================================================

async def _dashboard_start_flow(profile: Optional[str] = None) -> Dict[str, Any]:
    """Start Google Flow browser login flow."""
    import hermes_cli.web_server as ws
    sid, sess = ws._new_oauth_session("google-flow", "device_code", profile=profile)

    try:
        from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
    except ImportError:
        try:
            from bridge.flow.camofox_bridge import CamofoxFlowBridge
        except ImportError:
            from flow.camofox_bridge import CamofoxFlowBridge

    try:
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        try:
            from bridge.flow.account_pool import FlowAccountPoolManager
        except ImportError:
            FlowAccountPoolManager = None

    user_id = "google_flow_user"
    if FlowAccountPoolManager:
        try:
            pool = FlowAccountPoolManager()
            acc = pool.add_or_update_account("default")
            pool.set_active_account(acc.id)
            user_id = acc.user_id
        except Exception:
            pass

    bridge = CamofoxFlowBridge(user_id=user_id)

    def _open_and_monitor():
        try:
            # Ensure Camofox is up with desktop window
            bridge.ensure_server(interactive_mode="desktop")
            time.sleep(1.0)
            asyncio.run(bridge.ensure_tab())
            asyncio.run(bridge.navigate("https://labs.google/fx/tools/flow"))

            deadline = time.time() + ws._OAUTH_SESSION_TTL_SECONDS
            while time.time() < deadline:
                status = asyncio.run(bridge.check_status())
                if status.get("logged_in"):
                    email = status.get("email") or ""
                    if FlowAccountPoolManager and email:
                        try:
                            pool = FlowAccountPoolManager()
                            pool.add_or_update_account("default", email=email)
                        except Exception:
                            pass
                    with ws._oauth_sessions_lock:
                        s = ws._oauth_sessions.get(sid)
                        if s:
                            s["status"] = "approved"
                    logger.info("Google Flow login detected in Camofox!")
                    break
                time.sleep(2.0)
        except Exception as ex:
            logger.warning(f"Google Flow login monitor exception: {ex}")
            with ws._oauth_sessions_lock:
                s = ws._oauth_sessions.get(sid)
                if s:
                    s["status"] = "error"
                    s["error"] = str(ex)

    t = threading.Thread(target=_open_and_monitor, daemon=True, name=f"flow-login-{sid}")
    t.start()

    return {
        "session_id": sid,
        "flow": "device_code",
        "user_code": "Đăng nhập trên cửa sổ Camofox vừa mở (Không cần nhập code)",
        "verification_url": "/flow-helper",
        "expires_in": ws._OAUTH_SESSION_TTL_SECONDS,
        "poll_interval": 2,
    }


async def _dashboard_disconnect_flow() -> Dict[str, Any]:
    """Disconnect Google Flow session by closing active tab."""
    try:
        from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
    except ImportError:
        try:
            from bridge.flow.camofox_bridge import CamofoxFlowBridge
        except ImportError:
            from flow.camofox_bridge import CamofoxFlowBridge

    bridge = CamofoxFlowBridge()
    await bridge.close_tab()
    return {"ok": True, "provider": "google-flow"}


def _dashboard_start_pkce(profile: Optional[str] = None) -> Dict[str, Any]:
    """PKCE dashboard start logic for Antigravity."""
    import hermes_cli.web_server as ws
    try:
        from tools.antigravity_bridge.auth import (
            AUTH_ENDPOINT,
            OAUTH_SCOPES,
            AntigravityAuthManager,
            REDIRECT_HOST,
            CALLBACK_PATH,
            DEFAULT_REDIRECT_PORT,
        )
    except ImportError:
        from bridge.auth import (
            AUTH_ENDPOINT,
            OAUTH_SCOPES,
            AntigravityAuthManager,
            REDIRECT_HOST,
            CALLBACK_PATH,
            DEFAULT_REDIRECT_PORT,
        )

    verifier, challenge = ws._generate_pkce_pair()
    sid, sess = ws._new_oauth_session("antigravity", "device_code", profile=profile)
    sess["verifier"] = verifier
    state = secrets.token_hex(16)
    sess["state"] = state

    mgr = AntigravityAuthManager()
    client_id = mgr.get_client_id()
    redirect_uri = f"http://{REDIRECT_HOST}:{DEFAULT_REDIRECT_PORT}{CALLBACK_PATH}"
    sess["redirect_uri"] = redirect_uri

    def _run_callback_listener():
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == CALLBACK_PATH:
                    qs = urllib.parse.parse_qs(parsed.query)
                    code = qs.get("code", [None])[0]
                    if code:
                        try:
                            _dashboard_submit_pkce(sid, code, profile=profile)
                            self._send_html(
                                "<html><body style='font-family:sans-serif;text-align:center;padding-top:40px;background:#111;color:#eee;'>"
                                "<h2 style='color:#10b981;'>Antigravity OAuth Successful!</h2>"
                                "<p>You can now close this tab and return to Hermes Dashboard.</p>"
                                "</body></html>",
                                200,
                            )
                            return
                        except Exception as ex:
                            self._send_html(f"<h3>Error</h3><p>{ex}</p>", 500)
                            return
                self.send_response(404)
                self.end_headers()

            def _send_html(self, html: str, status: int):
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

            def log_message(self, format, *args):
                pass

        try:
            httpd = HTTPServer((REDIRECT_HOST, DEFAULT_REDIRECT_PORT), CallbackHandler)
            httpd.timeout = 2.0
            deadline = time.time() + 180.0
            while time.time() < deadline:
                httpd.handle_request()
                with ws._oauth_sessions_lock:
                    s = ws._oauth_sessions.get(sid)
                    if not s or s.get("status") in ("approved", "error"):
                        break
            httpd.server_close()
        except Exception as e:
            logger.debug(f"Antigravity OAuth callback server exception: {e}")

    t = threading.Thread(
        target=_run_callback_listener,
        daemon=True,
        name=f"antigravity-oauth-listener-{sid}",
    )
    t.start()

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    return {
        "session_id": sid,
        "flow": "device_code",
        "user_code": "Google Sign-In",
        "verification_url": auth_url,
        "expires_in": ws._OAUTH_SESSION_TTL_SECONDS,
        "poll_interval": 2,
    }


def _dashboard_submit_pkce(session_id: str, code: str, profile: Optional[str] = None):
    import hermes_cli.web_server as ws
    try:
        from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
    except ImportError:
        from bridge.auth import AntigravityAuthManager, AntigravityCredentials

    with ws._oauth_sessions_lock:
        sess = ws._oauth_sessions.get(session_id)
        if not sess or sess["provider"] != "antigravity" or sess.get("cancelled"):
            return {"ok": False, "error": "session invalid"}
        sess["status"] = "exchanging"
        verifier = sess.get("verifier")
        redirect_uri = sess.get("redirect_uri")

    mgr = AntigravityAuthManager()
    import requests
    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": mgr.get_client_id(),
                "client_secret": mgr.get_client_secret(),
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()

        creds = AntigravityCredentials(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=time.time() + payload.get("expires_in", 3599),
        )
        mgr.save_credentials(creds)
        _auto_start_bridge_daemon()

        with ws._oauth_sessions_lock:
            s = ws._oauth_sessions.get(session_id)
            if s:
                s["status"] = "approved"

        return {"ok": True, "status": "approved"}
    except Exception as e:
        with ws._oauth_sessions_lock:
            s = ws._oauth_sessions.get(session_id)
            if s:
                s["status"] = "error"
        raise e
