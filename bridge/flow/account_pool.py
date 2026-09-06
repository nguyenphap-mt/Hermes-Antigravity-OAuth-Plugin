"""Google Flow Multi-Account Pool & Auto-Rotation Manager.

Provides persistent multi-tenant account pooling for Google Flow:
1. Manages multiple Google accounts, each assigned to an isolated Camofox profile.
2. Tracks quota/credit status, usage counts, and cooldown timestamps.
3. Automatically selects the next available account when quota exhaustion occurs.
4. Thread-safe and persistent across Hermes updates (stored in ~/.hermes/auth/).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tools.antigravity_bridge.flow.account_pool")


def _get_hermes_auth_dir() -> Path:
    """Resolve Hermes auth directory reliably."""
    try:
        from hermes_constants import get_hermes_home
        base = get_hermes_home()
    except ImportError:
        base = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))

    auth_dir = base / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


DEFAULT_ACCOUNTS_FILE = _get_hermes_auth_dir() / "flow_accounts.json"


@dataclass
class FlowAccount:
    """Metadata for a registered Google Flow account."""

    id: str                                # Unique key, e.g. 'default', 'work', 'acc_2'
    user_id: str                           # Camofox profile key, e.g. 'google_flow_user_work'
    email: str = ""                        # User email captured from Google
    label: str = ""                        # Human-friendly label
    status: str = "active"                 # 'active', 'exhausted', 'disabled'
    exhausted_until: Optional[float] = None  # Unix timestamp when cooldown ends
    last_used: Optional[float] = None      # Unix timestamp of last generation
    total_creations: int = 0               # Total images/videos generated

    @property
    def is_available(self) -> bool:
        """Check if account is ready for use (active and not in cooldown)."""
        if self.status == "disabled":
            return False
        if self.status == "exhausted":
            if self.exhausted_until and time.time() > self.exhausted_until:
                return True  # Cooldown has expired
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FlowAccount:
        return cls(
            id=str(data.get("id", "default")),
            user_id=str(data.get("user_id", "google_flow_user")),
            email=str(data.get("email", "")),
            label=str(data.get("label", "")),
            status=str(data.get("status", "active")),
            exhausted_until=data.get("exhausted_until"),
            last_used=data.get("last_used"),
            total_creations=int(data.get("total_creations", 0)),
        )


class FlowAccountPoolManager:
    """Manages the pool of Google Flow accounts and auto-failover state."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or DEFAULT_ACCOUNTS_FILE
        self._lock = threading.Lock()
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Ensure storage file exists with at least a default account."""
        with self._lock:
            if not self.storage_path.exists():
                default_acc = FlowAccount(
                    id="default",
                    user_id="google_flow_user",
                    label="Primary Account",
                    status="active",
                )
                data = {
                    "active_account_id": "default",
                    "accounts": {"default": default_acc.to_dict()},
                }
                self._save_raw(data)

    def _load_raw(self) -> Dict[str, Any]:
        """Read raw json safely."""
        try:
            if self.storage_path.exists():
                return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Error loading flow_accounts.json: {e}")
        return {"active_account_id": "default", "accounts": {}}

    def _save_raw(self, data: Dict[str, Any]) -> None:
        """Write raw json atomically."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.storage_path.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_file.replace(self.storage_path)

    def list_accounts(self) -> List[FlowAccount]:
        """Return all registered accounts."""
        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})
            now = time.time()
            result = []
            modified = False

            for acc_data in accounts_dict.values():
                acc = FlowAccount.from_dict(acc_data)
                # Auto-recover exhausted accounts whose cooldown has elapsed
                if acc.status == "exhausted" and acc.exhausted_until and now > acc.exhausted_until:
                    acc.status = "active"
                    acc.exhausted_until = None
                    accounts_dict[acc.id] = acc.to_dict()
                    modified = True
                result.append(acc)

            if modified:
                data["accounts"] = accounts_dict
                self._save_raw(data)

            return result

    def get_active_account(self) -> FlowAccount:
        """Get the currently active account, or auto-pick the first available."""
        with self._lock:
            data = self._load_raw()
            active_id = data.get("active_account_id", "default")
            accounts_dict = data.get("accounts", {})

            if active_id in accounts_dict:
                acc = FlowAccount.from_dict(accounts_dict[active_id])
                if acc.is_available:
                    return acc

            # If active is not available, search for any available account
            for a_id, a_data in accounts_dict.items():
                acc = FlowAccount.from_dict(a_data)
                if acc.is_available:
                    data["active_account_id"] = a_id
                    self._save_raw(data)
                    logger.info(f"Auto-selected available account '{a_id}' as active.")
                    return acc

            # If none available, return active account anyway so error handling can act
            if active_id in accounts_dict:
                return FlowAccount.from_dict(accounts_dict[active_id])

            # Fallback default
            return FlowAccount(id="default", user_id="google_flow_user", label="Default")

    def get_next_available_account(self, exclude_id: Optional[str] = None) -> Optional[FlowAccount]:
        """Find the next available account in the pool, excluding exclude_id."""
        accounts = self.list_accounts()
        for acc in accounts:
            if exclude_id and acc.id == exclude_id:
                continue
            if acc.is_available:
                return acc
        return None

    def set_active_account(self, account_id: str) -> bool:
        """Explicitly switch the active account."""
        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})
            if account_id not in accounts_dict:
                logger.warning(f"Cannot switch: account '{account_id}' not found.")
                return False

            data["active_account_id"] = account_id
            self._save_raw(data)
            logger.info(f"Switched active Google Flow account to '{account_id}'.")
            return True

    def add_or_update_account(
        self,
        account_id: str,
        label: str = "",
        email: str = "",
        user_id: Optional[str] = None,
    ) -> FlowAccount:
        """Register or update an account in the pool."""
        account_id = account_id.strip().lower()
        if not user_id:
            user_id = f"google_flow_user_{account_id}" if account_id != "default" else "google_flow_user"

        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})

            if account_id in accounts_dict:
                acc = FlowAccount.from_dict(accounts_dict[account_id])
                if label:
                    acc.label = label
                if email:
                    acc.email = email
                acc.user_id = user_id
            else:
                acc = FlowAccount(
                    id=account_id,
                    user_id=user_id,
                    email=email,
                    label=label or f"Account {account_id}",
                    status="active",
                )

            accounts_dict[account_id] = acc.to_dict()
            data["accounts"] = accounts_dict
            self._save_raw(data)
            return acc

    def remove_account(self, account_id: str) -> bool:
        """Remove an account from the pool."""
        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})
            if account_id not in accounts_dict:
                return False

            del accounts_dict[account_id]
            data["accounts"] = accounts_dict

            # If we removed the active account, pick a new active
            if data.get("active_account_id") == account_id:
                data["active_account_id"] = next(iter(accounts_dict.keys()), "default")

            self._save_raw(data)
            return True

    def mark_account_exhausted(
        self,
        account_id: str,
        cooldown_seconds: int = 3600,
    ) -> Optional[FlowAccount]:
        """Mark account as exhausted/out of credits and auto-switch to next available."""
        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})
            if account_id in accounts_dict:
                acc = FlowAccount.from_dict(accounts_dict[account_id])
                acc.status = "exhausted"
                acc.exhausted_until = time.time() + cooldown_seconds
                accounts_dict[account_id] = acc.to_dict()
                logger.warning(
                    f"Account '{account_id}' marked EXHAUSTED until {time.ctime(acc.exhausted_until)}."
                )

            # Look for next available account
            next_acc = None
            for a_id, a_data in accounts_dict.items():
                cand = FlowAccount.from_dict(a_data)
                if cand.id != account_id and cand.is_available:
                    next_acc = cand
                    break

            if next_acc:
                data["active_account_id"] = next_acc.id
                logger.info(f"[Auto-Failover] Switched active account to '{next_acc.id}'.")

            data["accounts"] = accounts_dict
            self._save_raw(data)
            return next_acc

    def record_success(self, account_id: str) -> None:
        """Record successful generation on account."""
        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})
            if account_id in accounts_dict:
                acc = FlowAccount.from_dict(accounts_dict[account_id])
                acc.status = "active"
                acc.exhausted_until = None
                acc.last_used = time.time()
                acc.total_creations += 1
                accounts_dict[account_id] = acc.to_dict()
                data["accounts"] = accounts_dict
                self._save_raw(data)

    def reset_cooldown(self, account_id: str) -> bool:
        """Manually clear exhaustion status and restore account."""
        with self._lock:
            data = self._load_raw()
            accounts_dict = data.get("accounts", {})
            if account_id not in accounts_dict:
                return False

            acc = FlowAccount.from_dict(accounts_dict[account_id])
            acc.status = "active"
            acc.exhausted_until = None
            accounts_dict[account_id] = acc.to_dict()
            data["accounts"] = accounts_dict
            self._save_raw(data)
            return True
