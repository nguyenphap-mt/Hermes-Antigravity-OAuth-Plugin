"""Automated tests for Google Flow Multi-Account Pool & Auto-Failover."""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Ensure repo and plugin paths in sys.path
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
if _HERMES_DIR.exists():
    if str(_HERMES_DIR) in sys.path:
        sys.path.remove(str(_HERMES_DIR))
    sys.path.insert(0, str(_HERMES_DIR))

try:
    from bridge.flow.account_pool import FlowAccountPoolManager, FlowAccount
    from bridge.flow.generators import FlowCreditExhaustedError
    from bridge.flow.automation import GoogleFlowClient
except ImportError:
    from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager, FlowAccount
    from tools.antigravity_bridge.flow.generators import FlowCreditExhaustedError
    from tools.antigravity_bridge.flow.automation import GoogleFlowClient


class TestFlowAccountPool:
    """Test FlowAccountPoolManager operations and auto-failover mechanics."""

    @pytest.fixture
    def temp_pool(self, tmp_path):
        """Create an isolated test account pool with a temporary file."""
        storage = tmp_path / "flow_accounts_test.json"
        return FlowAccountPoolManager(storage_path=storage)

    def test_pool_initialization(self, temp_pool):
        """Pool must initialize with a primary default account."""
        accounts = temp_pool.list_accounts()
        assert len(accounts) == 1
        active = temp_pool.get_active_account()
        assert active.id == "default"
        assert active.is_available is True
        assert active.user_id == "google_flow_user"

    def test_add_and_switch_accounts(self, temp_pool):
        """Must allow adding multiple accounts and switching active account."""
        acc2 = temp_pool.add_or_update_account("work", email="work@company.com", label="Work Account")
        acc3 = temp_pool.add_or_update_account("personal", email="personal@gmail.com", label="Personal Account")

        accounts = temp_pool.list_accounts()
        assert len(accounts) == 3

        # Switch active
        assert temp_pool.set_active_account("work") is True
        active = temp_pool.get_active_account()
        assert active.id == "work"
        assert active.email == "work@company.com"
        assert active.user_id == "google_flow_user_work"

    def test_mark_account_exhausted_and_failover(self, temp_pool):
        """When active account runs out of credits, pool must auto-switch to next available."""
        temp_pool.add_or_update_account("acc_backup", email="backup@gmail.com", label="Backup")
        temp_pool.set_active_account("default")

        # Mark default as exhausted
        next_acc = temp_pool.mark_account_exhausted("default", cooldown_seconds=120)
        assert next_acc is not None
        assert next_acc.id == "acc_backup"

        # Check active account switched
        active = temp_pool.get_active_account()
        assert active.id == "acc_backup"

        # Default account should not be available
        accounts = {a.id: a for a in temp_pool.list_accounts()}
        assert accounts["default"].is_available is False
        assert accounts["default"].status == "exhausted"

    def test_cooldown_auto_recovery(self, temp_pool):
        """Accounts in cooldown must auto-recover once cooldown_until timestamp passes."""
        temp_pool.add_or_update_account("acc_test", email="test@gmail.com")
        temp_pool.mark_account_exhausted("acc_test", cooldown_seconds=60)

        # Force cooldown to past
        with temp_pool._lock:
            data = temp_pool._load_raw()
            data["accounts"]["acc_test"]["exhausted_until"] = time.time() - 5
            temp_pool._save_raw(data)

        # list_accounts should auto-recover it
        accounts = {a.id: a for a in temp_pool.list_accounts()}
        assert accounts["acc_test"].status == "active"
        assert accounts["acc_test"].is_available is True

    def test_client_auto_failover_execution(self, tmp_path):
        """GoogleFlowClient must transparently retry and succeed on next account when first fails with 429."""
        async def _run():
            storage = tmp_path / "flow_accounts_failover.json"
            pool = FlowAccountPoolManager(storage_path=storage)
            pool.remove_account("default")
            pool.add_or_update_account("acc_1", email="acc1@gmail.com", label="First")
            pool.add_or_update_account("acc_2", email="acc2@gmail.com", label="Second")
            pool.set_active_account("acc_1")

            client = GoogleFlowClient(media_dir=tmp_path)
            client.pool = pool
            client.bridge.switch_user = AsyncMock()

            # Mock operation: Fails with FlowCreditExhaustedError on acc_1, succeeds on acc_2
            call_count = 0

            async def mock_operation():
                nonlocal call_count
                call_count += 1
                curr_user = client.pool.get_active_account().id
                if curr_user == "acc_1":
                    raise FlowCreditExhaustedError("Quota exceeded 429", status_code=429)
                return {"success": True, "created_by": curr_user}

            result = await client._execute_with_failover("MockOp", mock_operation)

            assert result["success"] is True
            assert result["created_by"] == "acc_2"
            assert call_count == 2  # Retried exactly once on the second account

            # Verify acc_1 is marked exhausted and acc_2 has success recorded
            accounts = {a.id: a for a in pool.list_accounts()}
            assert accounts["acc_1"].status == "exhausted"
            assert accounts["acc_2"].total_creations == 1

        asyncio.run(_run())
