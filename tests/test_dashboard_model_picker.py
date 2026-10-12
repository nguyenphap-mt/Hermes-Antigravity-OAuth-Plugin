import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent
_HERMES_DIR = _THIS_DIR.parent / "hermes-agent"
for _p in [_THIS_DIR, _REPO_ROOT, _HERMES_DIR]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest

try:
    from plugin.injector import (
        _inject_antigravity_into_model_options,
        get_antigravity_auth_status,
        get_injection_health,
    )
except ImportError:
    mod = importlib.import_module("plugins.model-providers.antigravity.injector")
    _inject_antigravity_into_model_options = mod._inject_antigravity_into_model_options
    get_antigravity_auth_status = mod.get_antigravity_auth_status
    get_injection_health = mod.get_injection_health


class TestDashboardModelPickerIntegration:
    """Test suite for Dashboard Models Tab & Model Assignment Integration."""

    def test_inject_antigravity_into_model_options_structure(self):
        payload = {
            "providers": [
                {"slug": "openrouter", "name": "OpenRouter", "models": ["m1", "m2"]},
                {"slug": "gemini", "name": "Gemini", "models": ["g1"]},
            ],
            "provider": "openrouter",
            "model": "m1",
        }

        _inject_antigravity_into_model_options(payload)

        providers = payload["providers"]
        assert len(providers) == 3
        # Antigravity should be injected at top (index 0)
        ag_row = providers[0]
        assert ag_row["slug"] == "antigravity"
        assert "Google Antigravity" in ag_row["name"]
        assert len(ag_row["models"]) >= 6
        assert "gemini-3.7-flash-tiered" in ag_row["models"]
        assert "claude-sonnet-4-6" in ag_row["models"]
        assert "gpt-oss-120b-medium" in ag_row["models"]
        assert ag_row["base_url"] == "http://127.0.0.1:8100/v1"
        assert ag_row["is_current"] is False

    def test_inject_antigravity_is_current_when_selected(self):
        payload = {
            "providers": [],
            "provider": "antigravity",
            "model": "claude-sonnet-4-6",
        }

        _inject_antigravity_into_model_options(payload)

        ag_row = payload["providers"][0]
        assert ag_row["is_current"] is True

    def test_inject_idempotency_does_not_duplicate(self):
        payload = {"providers": []}
        _inject_antigravity_into_model_options(payload)
        assert len(payload["providers"]) == 1

        # Second injection should be a no-op
        _inject_antigravity_into_model_options(payload)
        assert len(payload["providers"]) == 1

    def test_apply_model_assignment_defaults_base_url_for_antigravity(self):
        from hermes_cli.web_server import _apply_main_model_assignment

        res = _apply_main_model_assignment(
            {},
            provider="antigravity",
            model="claude-sonnet-4-6",
            base_url="http://127.0.0.1:8100/v1",
            api_key="antigravity",
        )

        assert res["provider"] == "antigravity"
        assert res["default"] == "claude-sonnet-4-6"
        assert res["base_url"] == "http://127.0.0.1:8100/v1"
