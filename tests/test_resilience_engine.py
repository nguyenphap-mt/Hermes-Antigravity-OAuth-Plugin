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


if __name__ == "__main__":
    unittest.main()
