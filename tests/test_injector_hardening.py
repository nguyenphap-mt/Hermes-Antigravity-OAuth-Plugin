"""Automated test suite for Antigravity & Google Flow Injector Hardening."""

import inspect
import sys
import time
from pathlib import Path
import pytest

# Ensure repo and plugin paths in sys.path
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(1, str(_PLUGIN_DIR))

_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
if _HERMES_DIR.exists():
    if str(_HERMES_DIR) in sys.path:
        sys.path.remove(str(_HERMES_DIR))
    sys.path.insert(0, str(_HERMES_DIR))

import hermes_cli.web_server as ws
try:
    from plugin.injector import (
        patch_dashboard_ui,
        patch_cli_auth,
        get_injection_health,
        get_google_flow_auth_status,
        get_antigravity_auth_status,
        PATCH_MARKER,
    )
except ImportError:
    from injector import (
        patch_dashboard_ui,
        patch_cli_auth,
        get_injection_health,
        get_google_flow_auth_status,
        get_antigravity_auth_status,
        PATCH_MARKER,
    )


class TestInjectorHardening:
    """Test idempotency, signature preservation, and diagnostics."""

    def test_patch_idempotency(self):
        """Calling patch_dashboard_ui multiple times must NEVER duplicate cards or routes."""
        # Call patch multiple times
        for _ in range(5):
            patch_dashboard_ui()

        # Check catalog
        catalog = ws._build_oauth_catalog()
        antigravity_cards = [p for p in catalog if p.get("id") == "antigravity"]
        flow_cards = [p for p in catalog if p.get("id") == "google-flow"]

        assert len(antigravity_cards) == 1, f"Expected 1 antigravity card, got {len(antigravity_cards)}"
        assert len(flow_cards) == 1, f"Expected 1 google-flow card, got {len(flow_cards)}"

        # Check _OAUTH_PROVIDER_CATALOG tuple
        if hasattr(ws, "_OAUTH_PROVIDER_CATALOG"):
            cat_tuple = ws._OAUTH_PROVIDER_CATALOG
            tuple_flow = [p for p in cat_tuple if p.get("id") == "google-flow"]
            tuple_anti = [p for p in cat_tuple if p.get("id") == "antigravity"]
            assert len(tuple_flow) == 1, f"Expected 1 google-flow entry in tuple, got {len(tuple_flow)}"
            assert len(tuple_anti) == 1, f"Expected 1 antigravity entry in tuple, got {len(tuple_anti)}"

    def test_fastapi_signature_preservation(self):
        """FastAPI route endpoints must preserve original parameters via functools.wraps."""
        patch_dashboard_ui()
        app = ws.app

        start_route = next(
            (r for r in app.routes if getattr(r, "path", None) == "/api/providers/oauth/{provider_id}/start"),
            None,
        )
        assert start_route is not None, "Start route not found"

        sig = inspect.signature(start_route.endpoint)
        params = list(sig.parameters.keys())

        assert "provider_id" in params, f"provider_id missing from {params}"
        assert "request" in params, f"request missing from {params}"
        assert "profile" in params, f"profile missing from {params}"

    def test_get_injection_health(self):
        """get_injection_health() must accurately report patch health."""
        patch_dashboard_ui()
        patch_cli_auth()

        health = get_injection_health()
        assert health["web_server_detected"] is True
        assert health["catalog_patched"] is True
        assert health["start_route_patched"] is True
        assert health["is_healthy"] is True
        assert health["error"] is None

    def test_google_flow_fast_status_execution_time(self):
        """get_google_flow_auth_status must be instantaneous (< 0.5s) to avoid UI latency."""
        t0 = time.time()
        status = get_google_flow_auth_status()
        elapsed = time.time() - t0

        assert elapsed < 0.5, f"Status check took {elapsed:.2f}s, exceeding 0.5s threshold"
        assert isinstance(status, dict)
        assert "logged_in" in status
        assert "source_label" in status

    def test_antigravity_status_structure(self):
        """get_antigravity_auth_status must return compliant structure."""
        status = get_antigravity_auth_status()
        assert isinstance(status, dict)
        assert "logged_in" in status
        assert "source" in status
        assert "source_label" in status
