"""Unit tests for Multi-Tier Resilience Engine, Adaptive Tiered Cooldown, Micro-Spacing, and Service Sharding."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
for _p in [_PLUGIN_DIR, _HERMES_DIR]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from tools.antigravity_bridge.account_pool import AntigravityAccount, AntigravityAccountPoolManager
except ImportError:
    from bridge.account_pool import AntigravityAccount, AntigravityAccountPoolManager


class TestResilienceEngine(unittest.TestCase):
    """Test suite for Tiered Cooldown, Micro-spacing, and Service Sharding."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tokens_path = Path(self.temp_dir.name) / "antigravity_tokens.json"

        self.initial_data = {
            "active_account_email": "acc1@gmail.com",
            "rotation_strategy": "sharded",
            "accounts": {
                "acc1@gmail.com": {
                    "email": "acc1@gmail.com",
                    "access_token": "token_1",
                    "refresh_token": "refresh_1",
                    "expires_at": time.time() + 3600,
                    "project_id": "aicode-consumers",
                    "status": "active",
                    "assigned_role": "llm",
                    "consecutive_429_count": 0,
                    "last_request_time": 0.0,
                },
                "acc2@gmail.com": {
                    "email": "acc2@gmail.com",
                    "access_token": "token_2",
                    "refresh_token": "refresh_2",
                    "expires_at": time.time() + 3600,
                    "project_id": "aicode-consumers",
                    "status": "active",
                    "assigned_role": "image_gen",
                    "consecutive_429_count": 0,
                    "last_request_time": 0.0,
                },
            },
        }
        with open(self.tokens_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_data, f)

        self.pool = AntigravityAccountPoolManager(storage_path=self.tokens_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tiered_cooldown_escalation_and_reset(self) -> None:
        """Verify cooldown escalates from 60s -> 180s -> 900s, and resets on success."""
        email = "acc1@gmail.com"

        # 1st 429: should calculate 60s
        cd1 = self.pool.calculate_tiered_cooldown(email)
        self.assertEqual(cd1, 60.0)
        self.pool.mark_account_exhausted(email)
        acc1 = next(a for a in self.pool.list_accounts() if a.email == email)
        self.assertEqual(acc1.consecutive_429_count, 1)

        # 2nd consecutive 429: should calculate 180s
        cd2 = self.pool.calculate_tiered_cooldown(email)
        self.assertEqual(cd2, 180.0)
        self.pool.mark_account_exhausted(email)
        acc2 = next(a for a in self.pool.list_accounts() if a.email == email)
        self.assertEqual(acc2.consecutive_429_count, 2)

        # 3rd consecutive 429: should calculate 900s
        cd3 = self.pool.calculate_tiered_cooldown(email)
        self.assertEqual(cd3, 900.0)
        self.pool.mark_account_exhausted(email)
        acc3 = next(a for a in self.pool.list_accounts() if a.email == email)
        self.assertEqual(acc3.consecutive_429_count, 3)

        # On successful usage: consecutive_429_count resets to 0
        self.pool.record_account_usage(email, success=True)
        acc_reset = next(a for a in self.pool.list_accounts() if a.email == email)
        self.assertEqual(acc_reset.consecutive_429_count, 0)
        self.assertEqual(self.pool.calculate_tiered_cooldown(email), 60.0)

    def test_service_sharding_role_separation(self) -> None:
        """Verify Task-Based Sharding directs LLM to acc1 and image_gen to acc2."""
        llm_account = self.pool.get_account_for_service("llm")
        self.assertIsNotNone(llm_account)
        self.assertEqual(llm_account.email, "acc1@gmail.com")

        img_account = self.pool.get_account_for_service("image_gen")
        self.assertIsNotNone(img_account)
        self.assertEqual(img_account.email, "acc2@gmail.com")

    def test_service_sharding_graceful_borrowing(self) -> None:
        """Verify that when image_gen account is in cooldown, it gracefully borrows LLM account."""
        # Put acc2 into cooldown
        self.pool.mark_account_exhausted("acc2@gmail.com")

        # Now image_gen request should borrow acc1
        borrowed = self.pool.get_account_for_service("image_gen")
        self.assertIsNotNone(borrowed)
        self.assertEqual(borrowed.email, "acc1@gmail.com")

    def test_micro_spacing_guard(self) -> None:
        """Verify enforce_micro_spacing enforces minimal spacing between requests."""
        email = "acc1@gmail.com"
        # First call has no delay
        d1 = self.pool.enforce_micro_spacing(email, min_interval=0.2)
        self.assertEqual(d1, 0.0)

        # Immediate second call should enforce pacing delay
        t0 = time.time()
        d2 = self.pool.enforce_micro_spacing(email, min_interval=0.2)
        elapsed = time.time() - t0
        self.assertGreater(d2, 0.0)
        self.assertGreaterEqual(elapsed, 0.1)

    def test_in_flight_concurrency_leases(self) -> None:
        """Verify in-flight leases accurately track concurrent requests."""
        email = "acc1@gmail.com"
        self.assertEqual(self.pool.get_in_flight_count(email), 0)

        c1 = self.pool.acquire_lease(email)
        self.assertEqual(c1, 1)
        self.assertEqual(self.pool.get_in_flight_count(email), 1)

        c2 = self.pool.acquire_lease(email)
        self.assertEqual(c2, 2)
        self.assertEqual(self.pool.get_in_flight_count(email), 2)

        self.pool.release_lease(email)
        self.assertEqual(self.pool.get_in_flight_count(email), 1)

        self.pool.release_lease(email)
        self.assertEqual(self.pool.get_in_flight_count(email), 0)

    def test_set_and_get_rotation_strategies(self) -> None:
        """Verify setting valid strategies and rejecting invalid ones."""
        self.assertTrue(self.pool.set_rotation_strategy("round_robin"))
        self.assertEqual(self.pool.get_rotation_strategy(), "round_robin")

        self.assertTrue(self.pool.set_rotation_strategy("sharded"))
        self.assertEqual(self.pool.get_rotation_strategy(), "sharded")

        self.assertTrue(self.pool.set_rotation_strategy("failover"))
        self.assertEqual(self.pool.get_rotation_strategy(), "failover")

        self.assertFalse(self.pool.set_rotation_strategy("invalid_strategy"))

    def test_set_account_roles(self) -> None:
        """Verify setting custom account roles."""
        self.assertTrue(self.pool.set_account_role("acc1@gmail.com", "all"))
        acc = next(a for a in self.pool.list_accounts() if a.email == "acc1@gmail.com")
        self.assertEqual(acc.assigned_role, "all")

        self.assertFalse(self.pool.set_account_role("acc1@gmail.com", "unknown_role"))
        self.assertFalse(self.pool.set_account_role("nonexistent@gmail.com", "llm"))

    def test_proactive_soft_high_water_mark_routing(self) -> None:
        """Verify accounts with <= 10% quota for target model family are deprioritized before hitting 429."""
        # Set both accounts to role='all' so sharded/fill_first compare quota health
        self.pool.set_account_role("acc1@gmail.com", "all")
        self.pool.set_account_role("acc2@gmail.com", "all")

        # Update acc1 with low Claude quota (8% <= 10% threshold) and acc2 with healthy Claude quota (85%)
        self.pool.add_or_update_account({
            "email": "acc1@gmail.com",
            "quota_summary": {"claude_5h_pct": 8, "claude_weekly_pct": 60, "gemini_5h_pct": 95},
        })
        self.pool.add_or_update_account({
            "email": "acc2@gmail.com",
            "quota_summary": {"claude_5h_pct": 85, "claude_weekly_pct": 90, "gemini_5h_pct": 90},
        })

        # Even in fill_first when acc1 is active, requesting claude-sonnet-4-6 must proactively switch to acc2
        self.pool.set_rotation_strategy("fill_first")
        self.pool.set_active_account("acc1@gmail.com")
        chosen_claude = self.pool.get_account_for_service("llm", model="claude-sonnet-4-6")
        self.assertIsNotNone(chosen_claude)
        self.assertEqual(chosen_claude.email, "acc2@gmail.com")

        # Meanwhile, acc1 still has 95% Gemini quota, so requesting gemini-3.7-flash with acc1 active keeps acc1
        self.pool.set_active_account("acc1@gmail.com")
        chosen_gemini = self.pool.get_account_for_service("llm", model="gemini-3.7-flash")
        self.assertIsNotNone(chosen_gemini)
        self.assertEqual(chosen_gemini.email, "acc1@gmail.com")

    def test_model_family_scoped_cooldown_isolation(self) -> None:
        """Verify 429 on Claude cools down Claude family on that account without blocking Gemini."""
        self.pool.set_account_role("acc1@gmail.com", "all")
        self.pool.set_account_role("acc2@gmail.com", "all")
        self.pool.set_rotation_strategy("fill_first")
        self.pool.set_active_account("acc1@gmail.com")

        # Mark acc1 exhausted specifically on claude-sonnet-4-6
        self.pool.mark_account_exhausted(
            "acc1@gmail.com",
            cooldown_seconds=300.0,
            reason="HTTP 429 Quota Exhausted on claude-sonnet-4-6",
            model="claude-sonnet-4-6",
        )

        # Next Claude request must avoid acc1 and pick acc2
        claude_acc = self.pool.get_account_for_service("llm", model="claude-sonnet-4-6")
        self.assertIsNotNone(claude_acc)
        self.assertEqual(claude_acc.email, "acc2@gmail.com")

        # But if acc2 is excluded or we check availability for Gemini, acc1 is still available for Gemini!
        acc1_obj = self.pool.get_account("acc1@gmail.com")
        self.assertIsNotNone(acc1_obj)
        self.assertFalse(acc1_obj.is_available_for_model("claude-sonnet-4-6"))
        self.assertTrue(acc1_obj.is_available_for_model("gemini-3.7-flash"))

    def test_parse_retry_after_seconds_from_headers_and_google_rpc(self) -> None:
        """Verify parse_retry_after_seconds extracts exact cooldown from headers, Google RPC JSON, or ISO resetTime."""
        try:
            from tools.antigravity_bridge.account_pool import parse_retry_after_seconds
        except ImportError:
            from bridge.account_pool import parse_retry_after_seconds

        # 1. From HTTP Retry-After header
        d_hdr = parse_retry_after_seconds("", headers={"Retry-After": "42"})
        self.assertIsNotNone(d_hdr)
        self.assertGreaterEqual(d_hdr, 42.0)

        # 2. From Google RPC ErrorInfo / RetryInfo JSON body
        rpc_body = '{"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "75.5s"}]}}'
        d_rpc = parse_retry_after_seconds(rpc_body)
        self.assertIsNotNone(d_rpc)
        self.assertGreaterEqual(d_rpc, 75.5)

        # 3. Verify mark_account_exhausted honors retryDelay in reason
        self.pool.mark_account_exhausted("acc1@gmail.com", reason=rpc_body, model="claude-sonnet-4-6")
        acc1 = self.pool.get_account("acc1@gmail.com")
        self.assertIsNotNone(acc1)
        claude_cd_until = acc1.model_cooldowns.get("claude", 0.0)
        self.assertGreater(claude_cd_until - time.time(), 65.0)

    def test_plan_tier_weighted_health_score(self) -> None:
        """Verify Ultra and Pro accounts receive higher routing health score than Free accounts at equal quota %."""
        free_acc = AntigravityAccount(
            email="free@gmail.com",
            plan_type="free",
            quota_summary={"claude_5h_pct": 80, "claude_weekly_pct": 80},
        )
        pro_acc = AntigravityAccount(
            email="pro@gmail.com",
            plan_type="pro",
            tier_id="g1-pro-tier",
            quota_summary={"claude_5h_pct": 80, "claude_weekly_pct": 80},
        )
        ultra_acc = AntigravityAccount(
            email="ultra@gmail.com",
            plan_type="ultra",
            tier_id="g1-ultra-tier",
            quota_summary={"claude_5h_pct": 80, "claude_weekly_pct": 80},
        )
        s_free = free_acc.compute_routing_health_score("claude-sonnet-4-6")
        s_pro = pro_acc.compute_routing_health_score("claude-sonnet-4-6")
        s_ultra = ultra_acc.compute_routing_health_score("claude-sonnet-4-6")
        self.assertGreater(s_pro, s_free)
        self.assertGreater(s_ultra, s_pro)

        # Verify in_flight penalty lowers score
        s_pro_busy = pro_acc.compute_routing_health_score("claude-sonnet-4-6", in_flight=2)
        self.assertLess(s_pro_busy, s_free)

    def test_async_micro_spacing_non_blocking(self) -> None:
        """Verify enforce_micro_spacing_async paces requests asynchronously without blocking event loop."""
        import asyncio

        async def _run_check():
            d1 = await self.pool.enforce_micro_spacing_async("acc1@gmail.com", min_interval=0.15)
            self.assertEqual(d1, 0.0)
            d2 = await self.pool.enforce_micro_spacing_async("acc1@gmail.com", min_interval=0.15)
            self.assertGreater(d2, 0.0)

        asyncio.run(_run_check())

    def test_client_unpins_ya29_bearer_token_on_attempt_zero(self) -> None:
        """Verify AntigravityClient routes via account_pool on attempt 0 when bearer_token is ya29.*, but pins explicit email."""
        import asyncio
        try:
            from tools.antigravity_bridge.auth import AntigravityAuthManager
            from tools.antigravity_bridge.client import AntigravityClient
        except ImportError:
            from bridge.auth import AntigravityAuthManager
            from bridge.client import AntigravityClient

        # Configure round_robin with acc1 used recently so acc2 should be picked next by pool
        self.pool.set_account_role("acc1@gmail.com", "all")
        self.pool.set_account_role("acc2@gmail.com", "all")
        self.pool.set_rotation_strategy("round_robin")
        self.pool.record_account_usage("acc1@gmail.com", success=True)

        auth_mgr = AntigravityAuthManager(auth_file=self.tokens_path)
        client = AntigravityClient(auth_manager=auth_mgr)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": {
                "candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}]
            }
        }

        async def _fake_post(url, json=None, headers=None):
            return mock_resp

        client._http.post = _fake_post

        # Call with Hermes default ya29.token_1 (belonging to acc1) -> pool should still pick acc2 on attempt 0!
        asyncio.run(
            client.create_chat_completion(
                {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]},
                bearer_token="ya29.token_1_default_from_hermes_auth_json",
            )
        )
        acc2 = self.pool.get_account("acc2@gmail.com")
        self.assertEqual(acc2.total_requests, 1)
        self.assertEqual(self.pool.get_in_flight_count("acc2@gmail.com"), 0)


if __name__ == "__main__":
    unittest.main()
