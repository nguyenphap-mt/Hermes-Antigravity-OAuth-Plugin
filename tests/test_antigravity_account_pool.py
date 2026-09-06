"""Unit tests for Antigravity OAuth Multi-Account Pool & Auto-Failover."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
for _p in [_PLUGIN_DIR, _HERMES_DIR]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from tools.antigravity_bridge.account_pool import AntigravityAccount, AntigravityAccountPoolManager
    from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
    from tools.antigravity_bridge.client import AntigravityClient
except ImportError:
    from bridge.account_pool import AntigravityAccount, AntigravityAccountPoolManager
    from bridge.auth import AntigravityAuthManager, AntigravityCredentials
    from bridge.client import AntigravityClient


class TestAntigravityAccountPool(unittest.TestCase):
    """Test suite for AntigravityAccountPoolManager and AntigravityClient auto-failover."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tokens_path = Path(self.temp_dir.name) / "antigravity_tokens.json"

        # Seed test token data with two accounts
        self.initial_data = {
            "access_token": "ya29.token_user1",
            "refresh_token": "refresh_user1",
            "expires_at": time.time() + 3600,
            "email": "user1@gmail.com",
            "project_id": "aicode-consumers",
            "active_account_email": "user1@gmail.com",
            "rotation_strategy": "failover",
            "accounts": {
                "user1@gmail.com": {
                    "email": "user1@gmail.com",
                    "access_token": "ya29.token_user1",
                    "refresh_token": "refresh_user1",
                    "expires_at": time.time() + 3600,
                    "project_id": "aicode-consumers",
                    "status": "active",
                    "total_requests": 5,
                },
                "user2@gmail.com": {
                    "email": "user2@gmail.com",
                    "access_token": "ya29.token_user2",
                    "refresh_token": "refresh_user2",
                    "expires_at": time.time() + 3600,
                    "project_id": "aicode-consumers",
                    "status": "active",
                    "total_requests": 1,
                },
            },
        }
        with open(self.tokens_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_data, f, indent=2)

        self.pool = AntigravityAccountPoolManager(storage_path=self.tokens_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pool_initialization(self) -> None:
        """Verify accounts are discovered and active account is resolved correctly."""
        accounts = self.pool.list_accounts()
        self.assertEqual(len(accounts), 2)
        emails = {a.email for a in accounts}
        self.assertIn("user1@gmail.com", emails)
        self.assertIn("user2@gmail.com", emails)

        active = self.pool.get_active_account()
        self.assertIsNotNone(active)
        self.assertEqual(active.email, "user1@gmail.com")
        self.assertEqual(self.pool.get_rotation_strategy(), "failover")

    def test_switch_active_account(self) -> None:
        """Verify switching active account updates pointer and synchronizes root keys."""
        success = self.pool.set_active_account("user2@gmail.com")
        self.assertTrue(success)

        active = self.pool.get_active_account()
        self.assertEqual(active.email, "user2@gmail.com")

        # Verify root sync in json
        with open(self.tokens_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["active_account_email"], "user2@gmail.com")
        self.assertEqual(saved["email"], "user2@gmail.com")
        self.assertEqual(saved["access_token"], "ya29.token_user2")

    def test_mark_account_exhausted_and_auto_failover(self) -> None:
        """Verify marking active account exhausted switches active to next ready account."""
        next_acc = self.pool.mark_account_exhausted(
            "user1@gmail.com", cooldown_seconds=600.0, reason="HTTP 429"
        )
        self.assertIsNotNone(next_acc)
        self.assertEqual(next_acc.email, "user2@gmail.com")

        active = self.pool.get_active_account()
        self.assertEqual(active.email, "user2@gmail.com")

        # Verify user1 is in cooldown
        user1 = next(a for a in self.pool.list_accounts() if a.email == "user1@gmail.com")
        self.assertFalse(user1.is_available)
        self.assertEqual(user1.status, "cooling_down")
        self.assertIsNotNone(user1.exhausted_until)

    def test_cooldown_auto_recovery(self) -> None:
        """Verify an account whose cooldown timer expired recovers to active status."""
        # Set user1 exhausted in the past
        past_time = time.time() - 10.0
        with open(self.tokens_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["accounts"]["user1@gmail.com"]["status"] = "cooling_down"
        data["accounts"]["user1@gmail.com"]["exhausted_until"] = past_time
        with open(self.tokens_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # list_accounts should auto-recover it
        accounts = self.pool.list_accounts()
        user1 = next(a for a in accounts if a.email == "user1@gmail.com")
        self.assertTrue(user1.is_available)
        self.assertEqual(user1.status, "active")
        self.assertIsNone(user1.exhausted_until)

    def test_round_robin_rotation(self) -> None:
        """Verify round_robin strategy distributes requests across ready accounts."""
        self.pool.set_rotation_strategy("round_robin")
        self.assertEqual(self.pool.get_rotation_strategy(), "round_robin")

        # user1 and user2 both ready. Set user1 last_used older than user2.
        self.pool.record_account_usage("user1@gmail.com", success=True)
        time.sleep(0.01)
        self.pool.record_account_usage("user2@gmail.com", success=True)

        # In round_robin, least recently used is picked (user1)
        picked1 = self.pool.get_next_available_account()
        self.assertEqual(picked1.email, "user1@gmail.com")

        # Record usage on user1, next pick should be user2
        self.pool.record_account_usage("user1@gmail.com", success=True)
        picked2 = self.pool.get_next_available_account()
        self.assertEqual(picked2.email, "user2@gmail.com")

    def test_remove_account(self) -> None:
        """Verify removing an account deletes it from the pool."""
        success = self.pool.remove_account("user2@gmail.com")
        self.assertTrue(success)

        accounts = self.pool.list_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].email, "user1@gmail.com")

    def test_client_auto_failover_execution(self) -> None:
        """Verify AntigravityClient auto-fails over from 429 account to backup account."""
        import asyncio

        auth_mgr = AntigravityAuthManager(auth_file=self.tokens_path)
        client = AntigravityClient(auth_manager=auth_mgr)

        # Setup mock responses:
        # 1st attempt (user1@gmail.com): returns 429
        # 2nd attempt (user2@gmail.com): returns 200
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "RESOURCE_EXHAUSTED: Rate limit exceeded"

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Auto-failover success!"}],
                        },
                        "finishReason": "STOP",
                    }
                ]
            }
        }

        async def _mock_post(*args, **kwargs):
            # If headers contain user1's token -> return 429, else -> return 200
            headers = kwargs.get("headers", {})
            auth_header = headers.get("Authorization", "")
            if "token_user1" in auth_header:
                return mock_429
            return mock_200

        with patch.object(client._http, "post", side_effect=_mock_post):
            payload = {
                "model": "gemini-3.7-flash",
                "messages": [{"role": "user", "content": "Hello failover test"}],
            }
            res = asyncio.run(client.create_chat_completion(payload))

            # Assertion 1: Request succeeded transparently
            self.assertEqual(res["choices"][0]["message"]["content"], "Auto-failover success!")

            # Assertion 2: user1 was marked cooling_down
            user1 = next(a for a in client.account_pool.list_accounts() if a.email == "user1@gmail.com")
            self.assertEqual(user1.status, "cooling_down")

            # Assertion 3: Active account was switched to user2
            active = client.account_pool.get_active_account()
            self.assertEqual(active.email, "user2@gmail.com")


if __name__ == "__main__":
    unittest.main()
