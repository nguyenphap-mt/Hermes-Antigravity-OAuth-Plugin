import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_HERMES_AGENT = _REPO_ROOT.parent / "hermes-agent"
if _HERMES_AGENT.is_dir() and str(_HERMES_AGENT) not in sys.path:
    sys.path.insert(0, str(_HERMES_AGENT))

import pytest

try:
    from tools.antigravity_bridge.models import (
        BASELINE_MODELS,
        DiscoveredModel,
        ModelDiscoveryManager,
    )
except ImportError:
    from bridge.models import (
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
        assert target_id in {"gemini-3.8-flash-high", "gemini-3.8-flash-tiered"}

        target_id, meta = mgr.resolve_model("gemini-3.7-flash-low")
        assert target_id == "gemini-3.8-flash-low"

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

    def test_multi_account_pool_failover_on_403(self, tmp_path):
        import urllib.error
        from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

        auth_file = tmp_path / "antigravity_tokens.json"
        cache_file = tmp_path / "models_cache.json"
        auth_mgr = AntigravityAuthManager(auth_file=auth_file)
        pool = AntigravityAccountPoolManager(storage_path=auth_file)

        acc1 = AntigravityCredentials(
            access_token="tok-banned",
            refresh_token="ref-1",
            expires_at=time.time() + 3600,
            email="banned@example.com",
            project_id="aicode-consumers",
        )
        acc2 = AntigravityCredentials(
            access_token="tok-healthy",
            refresh_token="ref-2",
            expires_at=time.time() + 3600,
            email="healthy@example.com",
            project_id="aicode-consumers",
        )
        auth_mgr.save_credentials(acc1)
        auth_mgr.save_credentials(acc2)
        pool.set_active_account("banned@example.com")

        def side_effect(req, timeout=12.0):
            auth_hdr = req.headers.get("Authorization") or req.headers.get("authorization") or ""
            if "tok-banned" in auth_hdr:
                raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps({
                "models": {
                    "gemini-3.9-ultra-new": {
                        "displayName": "Gemini 3.9 Ultra New",
                        "recommended": True,
                    }
                }
            }).encode("utf-8")
            res = MagicMock()
            res.__enter__.return_value = mock_cm
            return res

        mgr = ModelDiscoveryManager(auth_manager=auth_mgr, cache_file=cache_file)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            models = mgr.get_discovered_models(force_refresh=True)

        ids = [m.id for m in models]
        assert "gemini-3.9-ultra-new" in ids

    def test_resolve_model_live_refresh_on_cache_miss(self, tmp_path):
        cache_file = tmp_path / "cache_miss.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.return_value = MagicMock(
            access_token="token-live", project_id="aicode-consumers", email="live@example.com"
        )
        mgr = ModelDiscoveryManager(auth_manager=mock_auth, cache_file=cache_file, ttl_seconds=3600.0)

        # Seed initial cache without the brand-new model
        mgr._save_cache_to_disk({
            "models": {"gemini-3.8-flash-high": {"displayName": "Gemini 3.8 Flash High", "recommended": True}},
            "project_id": "aicode-consumers",
            "email": "live@example.com",
        })

        # Request a newly released model not in the 1h cache -> should trigger live refresh
        live_payload = {
            "models": {
                "gemini-3.8-flash-high": {"displayName": "Gemini 3.8 Flash High", "recommended": True},
                "claude-opus-4-7-thinking": {"displayName": "Claude Opus 4.7 (Thinking)", "recommended": True},
            }
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(live_payload).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_cm

            resolved_id, meta = mgr.resolve_model("claude-opus-4-7-thinking")
            assert resolved_id == "claude-opus-4-7-thinking"
            assert mock_urlopen.called

    def test_discover_local_tokens_disabled(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityAuthManager
        mgr = AntigravityAuthManager(auth_file=tmp_path / "empty_tokens.json")
        assert mgr.discover_local_tokens() is None

    def test_clean_ide_headers_and_prompt_id_sync(self):
        from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
        from tools.antigravity_bridge.client import (
            build_antigravity_headers,
            build_code_assist_request,
        )

        prompt_id = "test-prompt-uuid-1234"
        traj_id = AntigravityFingerprint.get_trajectory_id()
        headers = build_antigravity_headers(
            access_token="tok-123",
            project_id="aicode-consumers",
            prompt_id=prompt_id,
            trajectory_id=traj_id,
        )
        ver, _, _ = AntigravityFingerprint.get_version_info()
        cl = AntigravityFingerprint.get_changelist()
        assert headers["User-Agent"].startswith(f"antigravity/{ver} (aidev_client; os_type=")
        assert f"cl={cl}" in headers["User-Agent"]
        assert headers["X-Goog-Api-Client"] == f"gl-go/1.24.0 gccl/{ver} antigravity/{ver}"
        assert headers["Accept-Encoding"] == "gzip"
        assert "Client-Metadata" in headers
        assert "x-activity-request-id" in headers
        assert headers["X-Aicode-Request-Id"] == headers["x-activity-request-id"]
        assert "X-Goog-User-Project" not in headers
        assert headers["X-Aicode-Prompt-Id"] == prompt_id
        assert headers["X-Aicode-Trajectory-Id"] == traj_id

        envelope = build_code_assist_request(
            {"model": "gemini-3.8-flash-high", "messages": [{"role": "system", "content": "Be concise"}, {"role": "user", "content": "Hi"}]},
            project_id="aicode-consumers",
            prompt_id=prompt_id,
            trajectory_id=traj_id,
        )
        assert envelope["userPromptId"] == prompt_id
        assert envelope["userAgent"] == "antigravity"
        assert envelope["requestType"] == "agent"
        assert envelope["requestId"].startswith(f"agent/{traj_id}/")
        assert envelope["project"] == "aicode-consumers"
        assert envelope["request"]["sessionId"] == traj_id
        assert "role" not in envelope["request"]["systemInstruction"]
        assert envelope["request"]["systemInstruction"]["parts"] == [{"text": "Be concise"}]

    def test_load_code_assist_and_onboard_user_handshake(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityAuthManager

        mgr = AntigravityAuthManager(auth_file=tmp_path / "tokens.json")
        captured_requests = []

        def fake_urlopen(req, timeout=10.0):
            body = json.loads(req.data.decode("utf-8"))
            captured_requests.append((req.full_url, body, dict(req.headers)))
            mock_cm = MagicMock()
            if ":loadCodeAssist" in req.full_url:
                mock_cm.read.return_value = json.dumps({
                    "allowedTiers": [{"id": "free-tier", "isDefault": True}],
                }).encode("utf-8")
            elif ":onboardUser" in req.full_url:
                mock_cm.read.return_value = json.dumps({
                    "done": True,
                    "response": {
                        "cloudaicompanionProject": {"id": "cloudaicompanion-test-999"}
                    },
                }).encode("utf-8")
            res = MagicMock()
            res.__enter__.return_value = mock_cm
            return res

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            pid = mgr.resolve_project_id("tok-handshake")

        assert pid == "cloudaicompanion-test-999"
        assert len(captured_requests) == 2
        load_url, load_body, _ = captured_requests[0]
        assert ":loadCodeAssist" in load_url
        assert load_body["metadata"]["ideType"] == "ANTIGRAVITY"
        assert load_body["metadata"]["platform"] == "PLATFORM_UNSPECIFIED"
        assert load_body["metadata"]["pluginType"] == "GEMINI"

        onboard_url, onboard_body, _ = captured_requests[1]
        assert ":onboardUser" in onboard_url
        assert onboard_body["tierId"] == "free-tier"
        assert onboard_body["metadata"]["ideType"] == "ANTIGRAVITY"
        assert onboard_body["metadata"]["platform"] == "PLATFORM_UNSPECIFIED"

    def test_cooldown_strictly_enforced_when_all_accounts_cooling_down(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

        auth_file = tmp_path / "antigravity_tokens.json"
        auth_mgr = AntigravityAuthManager(auth_file=auth_file)
        pool = AntigravityAccountPoolManager(storage_path=auth_file)

        acc = AntigravityCredentials(
            access_token="tok-cool",
            refresh_token="ref-cool",
            expires_at=time.time() + 3600,
            email="cooling@example.com",
            project_id="aicode-consumers",
        )
        auth_mgr.save_credentials(acc)
        pool.mark_account_exhausted("cooling@example.com", reason="HTTP 429", cooldown_seconds=120.0)

        # Pool must NEVER return a cooling_down account
        assert pool.get_account_for_service("llm") is None
        assert pool.get_next_available_account() is None

        # Auth manager must NEVER bypass pool cooldown by falling back to primary stored credentials
        with pytest.raises(RuntimeError, match=r"cooling.?down"):
            auth_mgr.resolve_valid_credentials()
        with pytest.raises(RuntimeError, match=r"cooling.?down"):
            auth_mgr.resolve_valid_credentials(bearer_token="cooling@example.com")

    def test_save_credentials_preserves_cooldown_and_disabled_state(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

        auth_file = tmp_path / "antigravity_tokens.json"
        auth_mgr = AntigravityAuthManager(auth_file=auth_file)
        pool = AntigravityAccountPoolManager(storage_path=auth_file)

        acc = AntigravityCredentials(
            access_token="tok-1",
            refresh_token="ref-1",
            expires_at=time.time() + 3600,
            email="preserve@example.com",
            project_id="aicode-consumers",
            managed_project_id="companion-proj-123",
        )
        auth_mgr.save_credentials(acc)
        pool.mark_account_exhausted("preserve@example.com", reason="HTTP 429", cooldown_seconds=300.0)

        # Simulate saving refreshed token for the same account
        refreshed = AntigravityCredentials(
            access_token="tok-2-refreshed",
            refresh_token="ref-1",
            expires_at=time.time() + 7200,
            email="preserve@example.com",
            project_id="aicode-consumers",
        )
        auth_mgr.save_credentials(refreshed)

        accounts = pool.list_accounts()
        assert len(accounts) == 1
        saved_acc = accounts[0]
        assert saved_acc.access_token == "tok-2-refreshed"
        assert saved_acc.status == "cooling_down"
        assert saved_acc.consecutive_429_count == 1
        assert saved_acc.managed_project_id == "companion-proj-123"
        assert not saved_acc.is_available

    def test_tos_violation_403_disables_account_immediately(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

        auth_file = tmp_path / "antigravity_tokens.json"
        auth_mgr = AntigravityAuthManager(auth_file=auth_file)
        pool = AntigravityAccountPoolManager(storage_path=auth_file)

        acc = AntigravityCredentials(
            access_token="tok-tos",
            refresh_token="ref-tos",
            expires_at=time.time() + 3600,
            email="tos@example.com",
            project_id="aicode-consumers",
        )
        auth_mgr.save_credentials(acc)
        pool.mark_account_exhausted("tos@example.com", reason="HTTP 403 TOS_VIOLATION")

        accounts = pool.list_accounts()
        assert accounts[0].status == "disabled"
        assert not accounts[0].is_available
        assert pool.get_account_for_service("llm") is None

    def test_no_self_ddos_recursion_and_negative_caching(self, tmp_path):
        cache_file = tmp_path / "neg_cache.json"
        mock_auth = MagicMock()
        mock_auth.resolve_valid_credentials.side_effect = RuntimeError("All cooling down")

        mgr = ModelDiscoveryManager(
            auth_manager=mock_auth,
            cache_file=cache_file,
            ttl_seconds=3600.0,
            is_bridge_server=True,
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            # 1st call: resolves candidate creds (once) -> fails -> sets negative memory cache
            models1 = mgr.fetch_models(force_refresh=False)
            assert len(models1) >= len(BASELINE_MODELS)
            assert mock_auth.resolve_valid_credentials.call_count == 1
            mock_urlopen.assert_not_called()

            # 2nd call: served directly from negative memory cache without calling auth_manager or network!
            models2 = mgr.fetch_models(force_refresh=False)
            assert len(models2) >= len(BASELINE_MODELS)
            assert mock_auth.resolve_valid_credentials.call_count == 1
            mock_urlopen.assert_not_called()

    def test_pkce_remote_session_start_and_submit(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityAuthManager

        auth_file = tmp_path / "mobile_tokens.json"
        auth_mgr = AntigravityAuthManager(auth_file=auth_file)
        session = auth_mgr.create_pkce_auth_session()

        assert session["session_id"]
        assert "https://accounts.google.com/o/oauth2/v2/auth?" in session["auth_url"]
        assert session["code_verifier"]
        assert session["state"]

        def fake_urlopen(req, timeout=10.0):
            mock_cm = MagicMock()
            if "oauth2.googleapis.com/token" in req.full_url:
                mock_cm.read.return_value = json.dumps({
                    "access_token": "tok-mobile-new",
                    "refresh_token": "ref-mobile-new",
                    "expires_in": 3600,
                }).encode("utf-8")
            elif "userinfo" in req.full_url:
                mock_cm.read.return_value = json.dumps({
                    "email": "mobileuser@example.com",
                }).encode("utf-8")
            elif ":loadCodeAssist" in req.full_url:
                mock_cm.read.return_value = json.dumps({
                    "cloudaicompanionProject": {"id": "companion-mobile-777"},
                    "currentTier": {"id": "pro-tier"},
                }).encode("utf-8")
            res = MagicMock()
            res.__enter__.return_value = mock_cm
            return res

        callback_url = f"http://127.0.0.1:51121/oauth-callback?state={session['state']}&code=4/0AbcDefGhi"
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            creds = auth_mgr.complete_pkce_auth_session(
                callback_or_code=callback_url,
                code_verifier=session["code_verifier"],
                redirect_uri=session["redirect_uri"],
                expected_state=session["state"],
            )

        assert creds.email == "mobileuser@example.com"
        assert creds.access_token == "tok-mobile-new"
        assert creds.managed_project_id == "companion-mobile-777"

    def test_account_pool_get_account_roles_strategies_and_promotion(self, tmp_path):
        from tools.antigravity_bridge.auth import AntigravityCredentials
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

        auth_file = tmp_path / "pool_audit.json"
        pool = AntigravityAccountPoolManager(storage_path=auth_file)

        c1 = AntigravityCredentials(
            access_token="tok-1",
            refresh_token="ref-1",
            expires_at=time.time() + 3600,
            email="acc1@example.com",
            project_id="aicode-consumers",
        )
        c2 = AntigravityCredentials(
            access_token="tok-2",
            refresh_token="ref-2",
            expires_at=time.time() + 3600,
            email="acc2@example.com",
            project_id="aicode-consumers",
        )
        pool.add_or_update_account(c1)
        pool.add_or_update_account(c2)

        assert pool.get_account("ACC1@example.com") is not None
        assert pool.get_account("acc1@example.com").email == "acc1@example.com"
        assert pool.get_account("missing@example.com") is None

        # Role assignment
        assert pool.set_account_role("acc2@example.com", "image_gen")
        assert pool.get_account("acc2@example.com").role == "image_gen"

        # All 4 UI rotation strategies + failover must be accepted
        for strat in ("fill_first", "round_robin", "least_used", "sharded", "failover"):
            assert pool.set_rotation_strategy(strat)
            assert pool.get_rotation_strategy() == strat

        # Auto-promotion when active account is disabled
        pool.set_active_account("acc1@example.com")
        pool.mark_account_disabled("acc1@example.com", reason="TOS_VIOLATION")
        active = pool.get_active_account()
        assert active is not None
        assert active.email == "acc2@example.com"

        # Re-login with reset_status=True restores disabled account to active
        pool.add_or_update_account(c1, reset_status=True)
        assert pool.get_account("acc1@example.com").status == "active"

    def test_probe_account_unlock_status_restores_unlocked_and_keeps_locked(self, tmp_path):
        import urllib.error
        from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

        auth_file = tmp_path / "unlock_probe.json"
        auth_mgr = AntigravityAuthManager(auth_file=auth_file)
        pool = AntigravityAccountPoolManager(storage_path=auth_file)

        c_locked = AntigravityCredentials(
            access_token="tok-locked",
            refresh_token="ref-locked",
            expires_at=time.time() + 3600,
            email="locked@example.com",
            project_id="aicode-consumers",
        )
        pool.add_or_update_account(c_locked)
        pool.mark_account_disabled("locked@example.com", reason="HTTP 403 TOS_VIOLATION")

        # 1. Still locked by Google -> returns unlocked=False and appeal_url
        err_payload = json.dumps({
            "error": {
                "code": 403,
                "message": "This service has been disabled in this account for violation of Terms of Service.",
                "details": [{
                    "reason": "TOS_VIOLATION",
                    "metadata": {"appeal_url": "https://forms.gle/hGzM9MEUv2azZsrb9"},
                }],
            }
        }).encode("utf-8")

        def locked_urlopen(req, timeout=12.0):
            import io
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(err_payload))

        with patch("urllib.request.urlopen", side_effect=locked_urlopen):
            res_locked = auth_mgr.probe_account_unlock_status("locked@example.com")

        assert res_locked["ok"] is True
        assert res_locked["unlocked"] is False
        assert res_locked["status"] == "disabled"
        assert res_locked["appeal_url"] == "https://forms.gle/hGzM9MEUv2azZsrb9"
        assert pool.get_account("locked@example.com").status == "disabled"

        # 2. Unlocked by Google -> returns unlocked=True and restores status='active'
        def unlocked_urlopen(req, timeout=12.0):
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps({
                "cloudaicompanionProject": "aicode-consumers",
                "currentTier": {"id": "free-tier"},
            }).encode("utf-8")
            res = MagicMock()
            res.__enter__.return_value = mock_cm
            return res

        with patch("urllib.request.urlopen", side_effect=unlocked_urlopen):
            res_unlocked = auth_mgr.probe_account_unlock_status("locked@example.com")

        assert res_unlocked["ok"] is True
        assert res_unlocked["unlocked"] is True
        assert res_unlocked["status"] == "active"
        assert pool.get_account("locked@example.com").status == "active"





