"""Google Antigravity OAuth Multi-Account Pool & Auto-Rotation Manager.

Provides persistent multi-account pooling, quota tracking, and auto-failover
for Google Antigravity OAuth accounts:
1. Manages multiple Google OAuth accounts (stored in ~/.hermes/auth/antigravity_tokens.json).
2. Supports two rotation strategies:
   - 'failover' (default): Uses active account until rate limit (429) or quota exhaustion occurs,
     then automatically fails over to the next ready account with a cooldown window.
   - 'round_robin': Evenly distributes requests across ready accounts to prevent per-minute rate limits.
3. Automatically recovers accounts after cooldown expiration.
4. Seamlessly maintains backward compatibility with legacy token readers by keeping root
   keys (access_token, refresh_token, email, etc.) synchronized with the active account.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tools.antigravity_bridge.account_pool")


def _get_hermes_auth_dir() -> Path:
    """Resolve platform-aware Hermes auth directory."""
    try:
        from hermes_constants import get_hermes_home
        base = get_hermes_home()
    except Exception:
        custom = os.getenv("HERMES_HOME")
        if custom:
            base = Path(custom).expanduser()
        elif sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
            base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local" / "hermes"
        else:
            base = Path.home() / ".hermes"

    auth_dir = base / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


DEFAULT_TOKENS_FILE = _get_hermes_auth_dir() / "antigravity_tokens.json"
DEFAULT_COOLDOWN_SECONDS = 900.0  # 15 minutes default cooldown on 429/quota exhaustion


@dataclass
class AntigravityAccount:
    """Metadata and state for an Antigravity OAuth account."""

    email: str
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    project_id: str = "aicode-consumers"
    managed_project_id: str = ""
    tier_id: str = ""
    source: str = "oauth_pkce"
    status: str = "active"                   # 'active', 'exhausted', 'cooling_down', 'disabled'
    exhausted_until: Optional[float] = None  # Unix timestamp when cooldown ends
    last_used: Optional[float] = None        # Unix timestamp of last request
    last_request_time: float = 0.0          # Unix timestamp for micro-spacing guard
    consecutive_429_count: int = 0          # Number of consecutive 429 errors for tiered cooldown
    assigned_role: str = "all"              # 'all', 'llm', 'image_gen'
    total_requests: int = 0                  # Cumulative request count
    failure_count: int = 0                   # Consecutive failure count

    @property
    def role(self) -> str:
        return self.assigned_role

    @role.setter
    def role(self, value: str):
        self.assigned_role = value

    @property
    def request_count(self) -> int:
        return self.total_requests

    @request_count.setter
    def request_count(self, value: int):
        self.total_requests = value

    @property
    def is_expired(self) -> bool:
        """Check if access token has expired or is close to expiring (within 2 min)."""
        if not self.access_token:
            return True
        if self.expires_at <= 0:
            return False
        return (self.expires_at - time.time()) < 120.0

    @property
    def is_available(self) -> bool:
        """Check if account is ready for use (active and not in cooldown)."""
        if self.status == "disabled":
            return False
        if self.status in {"exhausted", "cooling_down"}:
            if self.exhausted_until and time.time() >= self.exhausted_until:
                return True  # Cooldown expired, auto-recovered
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["updated_at"] = time.time()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AntigravityAccount:
        email = str(data.get("email", "")).strip().lower()
        return cls(
            email=email,
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=float(data.get("expires_at", 0.0) or 0.0),
            project_id=str(data.get("project_id", "aicode-consumers") or "aicode-consumers"),
            managed_project_id=str(data.get("managed_project_id", "") or ""),
            tier_id=str(data.get("tier_id", "") or ""),
            source=str(data.get("source", "oauth_pkce")),
            status=str(data.get("status", "active")),
            exhausted_until=float(data["exhausted_until"]) if data.get("exhausted_until") else None,
            last_used=float(data["last_used"]) if data.get("last_used") else None,
            last_request_time=float(data.get("last_request_time", 0.0) or 0.0),
            consecutive_429_count=int(data.get("consecutive_429_count", 0)),
            assigned_role=str(data.get("assigned_role", "all")),
            total_requests=int(data.get("total_requests", 0)),
            failure_count=int(data.get("failure_count", 0)),
        )


class AntigravityAccountPoolManager:
    """Thread-safe pool manager for Antigravity OAuth accounts and auto-failover."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or DEFAULT_TOKENS_FILE
        self._lock = threading.Lock()
        self._in_flight: Dict[str, int] = {}
        self._last_request_times: Dict[str, float] = {}
        self._ensure_initialized()

    def _load_raw(self) -> Dict[str, Any]:
        """Read raw json dictionary from tokens file."""
        if not self.storage_path.is_file():
            return {}
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug("Failed reading tokens file %s: %s", self.storage_path, e)
            return {}

    def _save_raw(self, data: Dict[str, Any]) -> None:
        """Atomically write dictionary to tokens file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.storage_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if os.name != "nt":
                os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(str(tmp), str(self.storage_path))
        except Exception as e:
            logger.error("Failed saving account pool to %s: %s", self.storage_path, e)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _ensure_initialized(self) -> None:
        """Ensure accounts dict exists and active_account_email is tracked."""
        with self._lock:
            data = self._load_raw()
            if not data:
                return

            accounts = data.get("accounts")
            if not isinstance(accounts, dict):
                accounts = {}
                if data.get("access_token") and data.get("email"):
                    em = data["email"].strip().lower()
                    accounts[em] = {**data, "email": em, "status": "active"}
                data["accounts"] = accounts

            # Track active_account_email
            active_email = data.get("active_account_email")
            if not active_email and data.get("email"):
                data["active_account_email"] = data["email"].strip().lower()
            elif not active_email and accounts:
                data["active_account_email"] = next(iter(accounts.keys()))

            if "rotation_strategy" not in data:
                data["rotation_strategy"] = "sharded"

            self._save_raw(data)

    def get_rotation_strategy(self) -> str:
        """Get rotation strategy ('sharded', 'round_robin', or 'failover')."""
        with self._lock:
            data = self._load_raw()
            return data.get("rotation_strategy", "sharded")

    def set_rotation_strategy(self, strategy: str) -> bool:
        """Set rotation strategy ('sharded', 'round_robin', or 'failover')."""
        st = strategy.strip().lower()
        if st not in {"sharded", "round_robin", "failover"}:
            return False
        with self._lock:
            data = self._load_raw()
            data["rotation_strategy"] = st
            self._save_raw(data)
            return True

    def set_account_role(self, email: str, role: str) -> bool:
        """Assign service role to account ('all', 'llm', 'image_gen')."""
        target = email.strip().lower()
        r = role.strip().lower()
        if r not in {"all", "llm", "image_gen"}:
            return False
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if isinstance(raw_accs, dict) and target in raw_accs:
                raw_accs[target]["assigned_role"] = r
                data["accounts"] = raw_accs
                self._save_raw(data)
                return True
        return False

    def calculate_tiered_cooldown(self, email: str) -> float:
        """Calculate dynamic tiered cooldown based on consecutive 429 errors.
        - 1st 429: 60.0s (transient burst limit / 1-minute window reset)
        - 2nd consecutive 429: 180.0s (rolling minute throttle)
        - 3rd+ consecutive 429: 900.0s (daily model quota exhaustion)
        """
        target = email.strip().lower()
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            count = 0
            if isinstance(raw_accs, dict) and target in raw_accs:
                count = int(raw_accs[target].get("consecutive_429_count", 0))

        if count <= 0:
            return 60.0
        elif count == 1:
            return 180.0
        else:
            return 900.0

    def enforce_micro_spacing(self, email: str, min_interval: float = 1.2) -> float:
        """Enforce minimal inter-request delay to prevent Google per-second Concurrency Burst 429s.
        Returns the delay slept in seconds.
        """
        target = email.strip().lower()
        delay = 0.0
        with self._lock:
            now = time.time()
            last = self._last_request_times.get(target, 0.0)
            if last <= 0.0:
                data = self._load_raw()
                raw_accs = data.get("accounts", {})
                if isinstance(raw_accs, dict) and target in raw_accs:
                    last = float(raw_accs[target].get("last_request_time", 0.0) or 0.0)

            elapsed = now - last
            if 0.0 < elapsed < min_interval:
                delay = min_interval - elapsed

            new_timestamp = now + delay
            self._last_request_times[target] = new_timestamp

        if delay > 0.0:
            logger.info("Micro-spacing guard: pacing account '%s' by %.2fs to prevent burst 429", target, delay)
            time.sleep(delay)

        return delay

    def acquire_lease(self, email: str) -> int:
        """Acquire in-flight request lease for concurrency tracking."""
        target = email.strip().lower()
        with self._lock:
            count = self._in_flight.get(target, 0) + 1
            self._in_flight[target] = count
            return count

    def release_lease(self, email: str) -> int:
        """Release in-flight request lease."""
        target = email.strip().lower()
        with self._lock:
            count = max(0, self._in_flight.get(target, 1) - 1)
            self._in_flight[target] = count
            return count

    def get_in_flight_count(self, email: str) -> int:
        """Check active concurrent requests for account."""
        target = email.strip().lower()
        with self._lock:
            return self._in_flight.get(target, 0)

    def list_accounts(self) -> List[AntigravityAccount]:
        """Return all registered Antigravity accounts, auto-recovering cooled-down accounts."""
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if not isinstance(raw_accs, dict):
                return []

            result: List[AntigravityAccount] = []
            modified = False
            now = time.time()

            for email_key, acct_dict in raw_accs.items():
                if not isinstance(acct_dict, dict):
                    continue
                acc = AntigravityAccount.from_dict(acct_dict)
                # Auto-recover if cooldown has expired
                if acc.status in {"exhausted", "cooling_down"} and acc.exhausted_until:
                    if now >= acc.exhausted_until:
                        acc.status = "active"
                        acc.exhausted_until = None
                        raw_accs[email_key]["status"] = "active"
                        raw_accs[email_key]["exhausted_until"] = None
                        modified = True
                result.append(acc)

            if modified:
                data["accounts"] = raw_accs
                self._save_raw(data)

            return result

    def get_active_account(self) -> Optional[AntigravityAccount]:
        """Get the currently designated active account."""
        accounts = self.list_accounts()
        if not accounts:
            return None

        with self._lock:
            data = self._load_raw()
            active_email = (data.get("active_account_email") or "").strip().lower()

        if active_email:
            for acc in accounts:
                if acc.email == active_email:
                    return acc

        return accounts[0]

    def set_active_account(self, email: str) -> bool:
        """Manually designate an account as active and sync root keys."""
        target = email.strip().lower()
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if not isinstance(raw_accs, dict) or target not in raw_accs:
                return False

            data["active_account_email"] = target
            acct_data = raw_accs[target]

            # Sync root keys for backward compatibility
            for k in ["access_token", "refresh_token", "expires_at", "email", "project_id", "managed_project_id", "tier_id", "source"]:
                if k in acct_data:
                    data[k] = acct_data[k]

            self._save_raw(data)
            logger.info("Switched active Antigravity account to: %s", target)
            return True

    def get_account_for_service(
        self,
        service_type: str = "all",  # 'llm', 'image_gen', 'all'
        exclude_emails: Optional[Set[str]] = None,
    ) -> Optional[AntigravityAccount]:
        """Select optimal account tailored for service type with Task-Based Sharding.
        - When pool has >= 2 ready accounts:
          * 'llm' defaults to Primary Account (or assigned_role='llm').
          * 'image_gen' defaults to Secondary Account (or assigned_role='image_gen').
          * Zero concurrency collision!
        - When pool has 1 ready account: returns that account.
        - Falls back gracefully if designated role account is cooling down.
        """
        exclude = {e.lower().strip() for e in (exclude_emails or set())}
        accounts = [a for a in self.list_accounts() if a.email not in exclude]
        if not accounts:
            return None

        strategy = self.get_rotation_strategy()

        ready_accounts = [a for a in accounts if a.is_available]
        if not ready_accounts:
            # Fallback to account whose cooldown ends soonest
            accounts_with_timer = [a for a in accounts if a.exhausted_until]
            if accounts_with_timer:
                return min(accounts_with_timer, key=lambda a: a.exhausted_until or 0)
            return accounts[0]

        if strategy == "sharded":
            if len(ready_accounts) >= 2:
                # Deterministic sorting so primary/secondary are stable
                ready_accounts.sort(key=lambda a: a.email)
                if service_type == "image_gen":
                    for a in ready_accounts:
                        if a.assigned_role == "image_gen":
                            return a
                    # Default: Secondary account (index 1) for image_gen
                    return ready_accounts[1]
                elif service_type == "llm":
                    for a in ready_accounts:
                        if a.assigned_role == "llm":
                            return a
                    # Default: Primary account (index 0) for llm
                    return ready_accounts[0]
                else:
                    ready_accounts.sort(key=lambda a: (a.last_used or 0.0))
                    return ready_accounts[0]

            return ready_accounts[0]

        elif strategy == "round_robin":
            ready_accounts.sort(key=lambda a: (a.last_used or 0.0))
            chosen = ready_accounts[0]
            self.set_active_account(chosen.email)
            return chosen

        else:  # 'failover'
            active = self.get_active_account()
            if active and active.is_available and active.email not in exclude:
                return active
            chosen = ready_accounts[0]
            self.set_active_account(chosen.email)
            return chosen

    def get_next_available_account(
        self,
        exclude_emails: Optional[Set[str]] = None,
    ) -> Optional[AntigravityAccount]:
        """Select the next available account based on active strategy and availability."""
        return self.get_account_for_service("all", exclude_emails=exclude_emails)

    def mark_account_exhausted(
        self,
        email: str,
        cooldown_seconds: Optional[float] = None,
        reason: str = "",
    ) -> Optional[AntigravityAccount]:
        """Mark an account exhausted/cooling_down with tiered cooldown and auto-failover."""
        target = email.strip().lower()
        if cooldown_seconds is None:
            cooldown_seconds = self.calculate_tiered_cooldown(target)

        now = time.time()
        cooldown_until = now + cooldown_seconds

        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if isinstance(raw_accs, dict) and target in raw_accs:
                raw_accs[target]["status"] = "cooling_down"
                raw_accs[target]["exhausted_until"] = cooldown_until
                raw_accs[target]["failure_count"] = int(raw_accs[target].get("failure_count", 0)) + 1
                raw_accs[target]["consecutive_429_count"] = int(raw_accs[target].get("consecutive_429_count", 0)) + 1
                consec = raw_accs[target]["consecutive_429_count"]
                data["accounts"] = raw_accs
                self._save_raw(data)
                logger.warning(
                    "Antigravity account '%s' entered tiered cooldown for %.0fs (consecutive_429=%d, until %.0f). Reason: %s",
                    target, cooldown_seconds, consec, cooldown_until, reason or "Rate limit / Quota reached"
                )

        # Automatically switch to next available account
        next_acc = self.get_next_available_account(exclude_emails={target})
        if next_acc:
            self.set_active_account(next_acc.email)
            logger.info("Auto-failover: switched active account to '%s'", next_acc.email)
            return next_acc

        return None

    def record_account_usage(self, email: str, success: bool = True) -> None:
        """Update last_used timestamp, micro-spacing timestamp, and request statistics."""
        target = email.strip().lower()
        now = time.time()
        with self._lock:
            self._last_request_times[target] = now
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if isinstance(raw_accs, dict) and target in raw_accs:
                acct = raw_accs[target]
                acct["last_used"] = now
                acct["last_request_time"] = now
                acct["total_requests"] = int(acct.get("total_requests", 0)) + 1
                if success:
                    acct["status"] = "active"
                    acct["exhausted_until"] = None
                    acct["failure_count"] = 0
                    acct["consecutive_429_count"] = 0
                else:
                    acct["failure_count"] = int(acct.get("failure_count", 0)) + 1
                data["accounts"] = raw_accs
                self._save_raw(data)

    def add_or_update_account(self, creds: Any) -> AntigravityAccount:
        """Register or update an account from AntigravityCredentials or dict."""
        if hasattr(creds, "email"):
            em = (creds.email or "primary").strip().lower()
            acc = AntigravityAccount(
                email=em,
                access_token=getattr(creds, "access_token", ""),
                refresh_token=getattr(creds, "refresh_token", ""),
                expires_at=getattr(creds, "expires_at", 0.0),
                project_id=getattr(creds, "project_id", "aicode-consumers") or "aicode-consumers",
                managed_project_id=getattr(creds, "managed_project_id", ""),
                tier_id=getattr(creds, "tier_id", ""),
                source=getattr(creds, "source", "oauth_pkce"),
                status="active",
            )
        elif isinstance(creds, dict):
            acc = AntigravityAccount.from_dict(creds)
        else:
            raise TypeError(f"Unsupported credentials type: {type(creds)}")

        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if not isinstance(raw_accs, dict):
                raw_accs = {}

            # Preserve tokens and counters if account already existed
            if acc.email in raw_accs:
                old = raw_accs[acc.email]
                if not acc.access_token and old.get("access_token"):
                    acc.access_token = old["access_token"]
                if not acc.refresh_token and old.get("refresh_token"):
                    acc.refresh_token = old["refresh_token"]
                if acc.expires_at <= 0 and old.get("expires_at"):
                    acc.expires_at = float(old["expires_at"])
                if not acc.project_id or acc.project_id == "aicode-consumers":
                    if old.get("project_id"):
                        acc.project_id = old["project_id"]
                acc.total_requests = old.get("total_requests", 0)
                acc.last_used = old.get("last_used")

            raw_accs[acc.email] = acc.to_dict()
            data["accounts"] = raw_accs

            # If no active account, make this one active
            if not data.get("active_account_email"):
                data["active_account_email"] = acc.email

            # Sync root keys if active
            if data.get("active_account_email") == acc.email:
                for k, v in acc.to_dict().items():
                    if k in {"access_token", "refresh_token", "expires_at", "email", "project_id", "managed_project_id", "tier_id", "source"}:
                        data[k] = v

            self._save_raw(data)
            logger.info("Saved account '%s' to Antigravity account pool.", acc.email)
            return acc

    def remove_account(self, email: str) -> bool:
        """Remove an account from the pool."""
        target = email.strip().lower()
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if not isinstance(raw_accs, dict) or target not in raw_accs:
                return False

            del raw_accs[target]
            data["accounts"] = raw_accs

            if data.get("active_account_email") == target:
                data["active_account_email"] = next(iter(raw_accs.keys()), "")
                if data["active_account_email"]:
                    active_data = raw_accs[data["active_account_email"]]
                    for k in ["access_token", "refresh_token", "expires_at", "email", "project_id"]:
                        data[k] = active_data.get(k, "")

            self._save_raw(data)
            logger.info("Removed account '%s' from Antigravity account pool.", target)
            return True
