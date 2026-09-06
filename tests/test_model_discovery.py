import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
for _p in [_PLUGIN_DIR, _HERMES_DIR]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest

try:
    from bridge.models import (
        BASELINE_MODELS,
        DiscoveredModel,
        ModelDiscoveryManager,
    )
except ImportError:
    from tools.antigravity_bridge.models import (
        BASELINE_MODELS,
        DiscoveredModel,
        ModelDiscoveryManager,
    )


class TestModelDiscovery:
    """Test suite for Dynamic Model Discovery & Quota Tracking."""

    def test_baseline_models_fallback(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.side_effect = RuntimeError("No credentials")

        mgr = ModelDiscoveryManager(auth_manager=mock_auth, cache_file=cache_file)
        models = mgr.get_discovered_models()

        assert len(models) >= len(BASELINE_MODELS)
        ids = {m.id for m in models}
        assert "gemini-3.7-flash-tiered" in ids
        assert "claude-sonnet-4-6" in ids
        assert "gpt-oss-120b-medium" in ids

    def test_fetch_models_parsing_and_sorting(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.return_value = MagicMock(
            access_token="fake-token",
            project_id="test-proj",
            email="tester@example.com",
        )

        mock_response = {
            "models": {
                "gemini-3.7-flash-tiered": {
                    "displayName": "Gemini 3.7 Flash Tiered",
                    "supportsImages": True,
                    "supportsThinking": True,
                    "thinkingBudget": 2048,
                    "minThinkingBudget": 32,
                    "maxTokens": 1048576,
                    "recommended": True,
                    "quotaInfo": {
                        "remainingFraction": 0.85,
                        "resetTime": "2026-09-04T00:00:00Z",
                    },
                },
                "claude-opus-4-6-thinking": {
                    "displayName": "Claude Opus 4.6 (Thinking)",
                    "supportsImages": True,
                    "supportsThinking": True,
                    "thinkingBudget": 8192,
                    "minThinkingBudget": 100,
                    "maxTokens": 250000,
                    "recommended": True,
                    "quotaInfo": {
                        "remainingFraction": 0.15,
                        "resetTime": "2026-09-04T12:00:00Z",
                    },
                },
                "basic-model": {
                    "displayName": "Basic Model",
                    "recommended": False,
                },
            }
        }

        mgr = ModelDiscoveryManager(auth_manager=mock_auth, cache_file=cache_file)
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_cm

            models = mgr.get_discovered_models(force_refresh=True)

        assert len(models) == 3
        # Recommended models should come first
        assert models[0].recommended is True
        assert models[1].recommended is True
        assert models[2].recommended is False

        opus = next(m for m in models if m.id == "claude-opus-4-6-thinking")
        assert opus.quota_fraction == 0.15
        assert opus.thinking_budget == 8192
        assert opus.supports_thinking is True

    def test_cache_save_and_ttl_expiration(self, tmp_path):
        cache_file = tmp_path / "cache_ttl.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.return_value = MagicMock(
            access_token="token", project_id="proj", email="t@e.com"
        )

        mgr = ModelDiscoveryManager(auth_manager=mock_auth, cache_file=cache_file, ttl_seconds=2.0)

        # 1. First fetch saves to disk
        mock_response = {"models": {"model-a": {"displayName": "Model A"}}}
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_cm

            res1 = mgr.fetch_models(force_refresh=False)
            assert "model-a" in res1
            assert cache_file.exists()

        # 2. Second fetch within TTL reads from cache (urlopen should NOT be called)
        with patch("urllib.request.urlopen") as mock_urlopen:
            res2 = mgr.fetch_models(force_refresh=False)
            assert "model-a" in res2
            mock_urlopen.assert_not_called()

        # 3. Simulate expired cache
        time.sleep(2.1)
        mock_response2 = {"models": {"model-b": {"displayName": "Model B"}}}
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_response2).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_cm

            res3 = mgr.fetch_models(force_refresh=False)
            assert "model-b" in res3

    def test_resolve_model_aliases(self, tmp_path):
        cache_file = tmp_path / "cache_alias.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.side_effect = RuntimeError("No credentials")
        mgr = ModelDiscoveryManager(auth_manager=mock_auth, cache_file=cache_file)

        # Using baseline models
        target_id, meta = mgr.resolve_model("gemini-3.7-flash")
        assert target_id == "gemini-3.7-flash-tiered"

        target_id, meta = mgr.resolve_model("claude-opus")
        assert target_id == "claude-opus-4-6-thinking"

        target_id, meta = mgr.resolve_model("gpt-oss")
        assert target_id == "gpt-oss-120b-medium"

        target_id, meta = mgr.resolve_model("claude-sonnet-4-6")
        assert target_id == "claude-sonnet-4-6"

    def test_list_openai_models_structure(self, tmp_path):
        cache_file = tmp_path / "cache_openai.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.side_effect = RuntimeError("No credentials")
        mgr = ModelDiscoveryManager(auth_manager=mock_auth, cache_file=cache_file)

        openai_models = mgr.list_openai_models()
        assert len(openai_models) > 0
        first = openai_models[0]
        assert "id" in first
        assert first["object"] == "model"
        assert first["owned_by"] == "antigravity"
        assert "supports_thinking" in first
        assert "max_tokens" in first
