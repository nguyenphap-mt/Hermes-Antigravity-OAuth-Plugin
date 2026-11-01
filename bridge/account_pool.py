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

import asyncio
import json
import logging
import os
import re
import shutil
import stat
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
SOFT_QUOTA_HIGH_WATER_MARK_PCT = 10.0  # Proactive switch threshold when remaining quota <= 10%
PLAN_WEIGHTS: Dict[str, float] = {
    "ultra": 1.5,
    "pro": 1.25,
    "free": 1.0,
}


def resolve_model_family(model_id: str = "") -> str:
    """Resolve model identifier into quota bucket family ('claude', 'gemini', or 'all')."""
    if not model_id or not str(model_id).strip():
        return "all"
    m = str(model_id).strip().lower()
    if any(tok in m for tok in ("claude", "gpt", "o1", "o3", "3p", "anthropic")):
        return "claude"
    return "gemini"


def parse_retry_after_seconds(
    error_body: str = "",
    headers: Optional[Dict[str, Any]] = None,
    reset_time_iso: Optional[str] = None,
) -> Optional[float]:
    """Extract exact server-reported retry cooldown in seconds from headers, Google RPC details, or ISO resetTime."""
    candidates: List[float] = []

    # 1. Check HTTP Retry-After header
    if isinstance(headers, dict):
        for k, v in headers.items():
            if str(k).strip().lower() == "retry-after" and v is not None:
                raw_val = str(v).strip()
                try:
                    sec = float(raw_val)
                    if sec > 0:
                        candidates.append(sec)
                except ValueError:
                    pass

    # 2. Check Google RPC RetryInfo / ErrorInfo JSON or text body
    body_str = str(error_body or "")
    if body_str:
        # Match "retryDelay": "75.5s" or "quotaResetDelay": "120s"
        for match in re.finditer(r'"(?:retryDelay|quotaResetDelay)"\s*:\s*"([0-9]+(?:\.[0-9]+)?)s"', body_str):
            try:
                sec = float(match.group(1))
                if sec > 0:
                    candidates.append(sec)
            except ValueError:
                pass

        # Match ISO timestamp in quotaResetTimeStamp or resetTime
        if not reset_time_iso:
            iso_match = re.search(
                r'"(?:quotaResetTimeStamp|resetTime)"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2}T[^"]+)"',
                body_str,
            )
            if iso_match:
                reset_time_iso = iso_match.group(1)

    # 3. Check explicit ISO-8601 resetTime
    if reset_time_iso:
        try:
            iso_clean = str(reset_time_iso).strip()
            if iso_clean.endswith("Z"):
                iso_clean = iso_clean[:-1] + "+00:00"
            dt = datetime.fromisoformat(iso_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = dt.timestamp() - time.time()
            if delta > 0:
                candidates.append(delta)
        except Exception:
            pass

    if not candidates:
        return None
    best = max(candidates)
    return max(1.0, min(best, 86400.0))


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
    plan_name: str = ""                     # 'Google AI Ultra', 'Google AI Pro', 'Free Tier'
    plan_type: str = "free"                 # 'ultra', 'pro', 'free'
    quota_summary: Dict[str, Any] = field(default_factory=dict)
    model_cooldowns: Dict[str, float] = field(default_factory=dict)

    @property
    def computed_plan_type(self) -> str:
        """Normalized plan tier: 'ultra' | 'pro' | 'free'."""
        name = (self.plan_name or "").lower()
        tier = (self.tier_id or "").lower()
        if "ultra" in name or "ultra" in tier:
            return "ultra"
        if "pro" in name or "pro" in tier:
            return "pro"
        if self.plan_type in {"ultra", "pro"}:
            return self.plan_type
        return "free"

    @property
    def display_plan_name(self) -> str:
        """User-friendly plan display name."""
        pt = self.computed_plan_type
        raw = (self.plan_name or "").strip()
        if raw and raw.lower() not in {"free", "free tier", "antigravity starter quota"}:
            return raw
        if pt == "ultra":
            return "Google AI Ultra"
        if pt == "pro":
            return "Google AI Pro"
        return "Free Tier"

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
    def effective_project_id(self) -> str:
        """Return managed companion project ID first, falling back to project_id."""
        if self.managed_project_id and self.managed_project_id != "aicode-consumers":
            return self.managed_project_id
        if self.project_id and self.project_id != "aicode-consumers":
            return self.project_id
        return self.managed_project_id or self.project_id or "aicode-consumers"

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

    def is_available_for_model(self, model_id: str = "") -> bool:
        """Check if account is available for a specific model family ('claude' vs 'gemini')."""
        if self.status == "disabled":
            return False
        now = time.time()
        family = resolve_model_family(model_id)
        active_family_cds = {
            k: float(v)
            for k, v in (self.model_cooldowns or {}).items()
            if v is not None and float(v) > now
        }
        if family in {"claude", "gemini"}:
            if family in active_family_cds:
                return False
            if active_family_cds:
                # Cooldown is scoped to another model family; this family remains available
                return True
        return self.is_available

    def get_remaining_quota_pct(self, model_id: str = "") -> float:
        """Return bottleneck remaining quota percentage (0..100) for the target model family."""
        qs = self.quota_summary or {}
        if not isinstance(qs, dict) or not qs:
            return 100.0
        family = resolve_model_family(model_id)
        if family == "claude":
            keys = ("claude_5h_pct", "claude_weekly_pct")
        elif family == "gemini":
            keys = ("gemini_5h_pct", "gemini_weekly_pct")
        else:
            keys = ("claude_5h_pct", "claude_weekly_pct", "gemini_5h_pct", "gemini_weekly_pct")

        vals: List[float] = []
        for k in keys:
            v = qs.get(k)
            if v is not None:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    pass
        return min(vals) if vals else 100.0

    def compute_routing_health_score(self, model_id: str = "", in_flight: int = 0) -> float:
        """Compute composite routing score combining remaining quota %, plan tier weight, and in-flight load."""
        rem_pct = self.get_remaining_quota_pct(model_id)
        plan_weight = PLAN_WEIGHTS.get(self.computed_plan_type, 1.0)
        base_score = rem_pct * plan_weight
        penalty = (max(0, int(in_flight)) * 25.0) + (max(0, int(self.consecutive_429_count)) * 20.0)
        return round(base_score - penalty, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["updated_at"] = time.time()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AntigravityAccount:
        email = str(data.get("email", "")).strip().lower()
        tier_id = str(data.get("tier_id", "") or "")
        raw_plan_name = str(data.get("plan_name", "") or "")
        raw_plan_type = str(data.get("plan_type", "") or "")

        p_low = raw_plan_name.lower()
        t_low = tier_id.lower()
        if "ultra" in p_low or "ultra" in t_low:
            plan_type = "ultra"
            plan_name = raw_plan_name or "Google AI Ultra"
        elif "pro" in p_low or "pro" in t_low:
            plan_type = "pro"
            plan_name = raw_plan_name or "Google AI Pro"
        elif raw_plan_type in {"ultra", "pro"}:
            plan_type = raw_plan_type
            plan_name = raw_plan_name or ("Google AI Ultra" if plan_type == "ultra" else "Google AI Pro")
        else:
            plan_type = "free"
            plan_name = raw_plan_name or "Free Tier"

        raw_mc = data.get("model_cooldowns")
        model_cooldowns: Dict[str, float] = {}
        if isinstance(raw_mc, dict):
            for k, v in raw_mc.items():
                if v is not None:
                    try:
                        model_cooldowns[str(k).strip().lower()] = float(v)
                    except (TypeError, ValueError):
                        pass

        return cls(
            email=email,
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=float(data.get("expires_at", 0.0) or 0.0),
            project_id=str(data.get("project_id", "aicode-consumers") or "aicode-consumers"),
            managed_project_id=str(data.get("managed_project_id", "") or ""),
            tier_id=tier_id,
            source=str(data.get("source", "oauth_pkce")),
            status=str(data.get("status", "active")),
            exhausted_until=float(data["exhausted_until"]) if data.get("exhausted_until") else None,
            last_used=float(data["last_used"]) if data.get("last_used") else None,
            last_request_time=float(data.get("last_request_time", 0.0) or 0.0),
            consecutive_429_count=int(data.get("consecutive_429_count", 0)),
            assigned_role=str(data.get("assigned_role", "all")),
            total_requests=int(data.get("total_requests", 0)),
            failure_count=int(data.get("failure_count", 0)),
            plan_name=plan_name,
            plan_type=plan_type,
            quota_summary=dict(data.get("quota_summary", {}) or {}) if isinstance(data.get("quota_summary"), dict) else {},
            model_cooldowns=model_cooldowns,
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
        for attempt in range(2):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                if attempt == 0:
                    time.sleep(0.025)
                    continue
                logger.debug("Failed reading tokens file %s: %s", self.storage_path, e)
                return {}
        return {}

    def _save_raw(self, data: Dict[str, Any]) -> None:
        """Atomically write dictionary to tokens file using process+thread-unique temp file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.storage_path.with_name(f"{self.storage_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
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
        """Ensure accounts dict exists and active_account_email is tracked (saving only when modified)."""
        with self._lock:
            data = self._load_raw()
            if not data:
                return

            dirty = False
            accounts = data.get("accounts")
            if isinstance(accounts, list):
                converted: Dict[str, Any] = {}
                for item in accounts:
                    if isinstance(item, dict) and item.get("email"):
                        em = str(item["email"]).strip().lower()
                        converted[em] = {**item, "email": em, "status": item.get("status") or "active"}
                accounts = converted
                data["accounts"] = accounts
                dirty = True
            elif not isinstance(accounts, dict):
                accounts = {}
                if data.get("access_token") and data.get("email"):
                    em = data["email"].strip().lower()
                    accounts[em] = {**data, "email": em, "status": "active"}
                data["accounts"] = accounts
                dirty = True

            # Track active_account_email
            active_email = data.get("active_account_email")
            if not active_email and data.get("email"):
                data["active_account_email"] = data["email"].strip().lower()
                dirty = True
            elif not active_email and accounts:
                data["active_account_email"] = next(iter(accounts.keys()))
                dirty = True

            if "rotation_strategy" not in data:
                data["rotation_strategy"] = "sharded"
                dirty = True

            if dirty:
                self._save_raw(data)

    def get_rotation_strategy(self) -> str:
        """Get rotation strategy ('sharded', 'round_robin', 'fill_first', 'least_used', or 'failover')."""
        with self._lock:
            data = self._load_raw()
            return data.get("rotation_strategy", "sharded")

    def set_rotation_strategy(self, strategy: str) -> bool:
        """Set rotation strategy ('sharded', 'round_robin', 'fill_first', 'least_used', or 'failover')."""
        st = strategy.strip().lower()
        if st not in {"sharded", "round_robin", "fill_first", "least_used", "failover"}:
            return False
        with self._lock:
            data = self._load_raw()
            data["rotation_strategy"] = st
            self._save_raw(data)
            return True

    def _save_pool(self) -> None:
        """Compatibility helper for external callers expecting _save_pool()."""
        with self._lock:
            data = self._load_raw()
            if data:
                self._save_raw(data)

    def get_account(self, email: str) -> Optional[AntigravityAccount]:
        """Get a specific account by email (case-insensitive), or None if not found."""
        target = (email or "").strip().lower()
        if not target:
            return None
        for acc in self.list_accounts():
            if acc.email == target:
                return acc
        return None

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

    def _reserve_micro_spacing_delay(self, email: str, min_interval: float = 1.8) -> Tuple[str, float]:
        """Compute and reserve the next request slot timestamp inside lock without sleeping."""
        import random
        target = email.strip().lower()
        delay = 0.0
        jitter = 0.0 if os.environ.get("PYTEST_CURRENT_TEST") else random.uniform(0.15, 0.55)
        effective_interval = min_interval + jitter
        with self._lock:
            now = time.time()
            last = self._last_request_times.get(target, 0.0)
            if last <= 0.0:
                data = self._load_raw()
                raw_accs = data.get("accounts", {})
                if isinstance(raw_accs, dict) and target in raw_accs:
                    last = float(raw_accs[target].get("last_request_time", 0.0) or 0.0)

            elapsed = now - last
            if 0.0 < elapsed < effective_interval:
                delay = effective_interval - elapsed

            new_timestamp = now + delay
            self._last_request_times[target] = new_timestamp
        return target, delay

    def enforce_micro_spacing(self, email: str, min_interval: float = 1.8) -> float:
        """Enforce minimal inter-request delay with natural jitter to prevent burst 429s.
        Returns the delay slept in seconds.
        """
        target, delay = self._reserve_micro_spacing_delay(email, min_interval=min_interval)
        if delay > 0.0:
            logger.info("Micro-spacing guard: pacing account '%s' by %.2fs to prevent burst 429", target, delay)
            time.sleep(delay)
        return delay

    async def enforce_micro_spacing_async(self, email: str, min_interval: float = 1.0) -> float:
        """Asynchronously enforce minimal inter-request delay without blocking the asyncio event loop."""
        target, delay = self._reserve_micro_spacing_delay(email, min_interval=min_interval)
        if delay > 0.0:
            logger.info("Async micro-spacing guard: pacing account '%s' by %.2fs to prevent burst 429", target, delay)
            await asyncio.sleep(delay)
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
                # Clean up expired model_cooldowns
                if acc.model_cooldowns:
                    active_cds = {k: v for k, v in acc.model_cooldowns.items() if v and now < float(v)}
                    if len(active_cds) != len(acc.model_cooldowns):
                        acc.model_cooldowns = active_cds
                        raw_accs[email_key]["model_cooldowns"] = active_cds
                        modified = True

                # Auto-recover if cooldown has expired (never auto-recover 'disabled')
                if acc.status in {"exhausted", "cooling_down"} and acc.exhausted_until:
                    if now >= acc.exhausted_until and not acc.model_cooldowns:
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
        """Get the currently designated active account, auto-promoting a healthy account if the active one is disabled."""
        accounts = self.list_accounts()
        if not accounts:
            return None

        with self._lock:
            data = self._load_raw()
            active_email = (data.get("active_account_email") or "").strip().lower()

        active_acc: Optional[AntigravityAccount] = None
        if active_email:
            for acc in accounts:
                if acc.email == active_email:
                    active_acc = acc
                    break

        if active_acc and active_acc.status != "disabled":
            return active_acc

        for acc in accounts:
            if acc.is_available:
                self.set_active_account(acc.email)
                return acc

        return active_acc or accounts[0]

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
            for k in [
                "access_token", "refresh_token", "expires_at", "email",
                "project_id", "managed_project_id", "tier_id", "source",
                "plan_name", "plan_type", "quota_summary"
            ]:
                if k in acct_data:
                    data[k] = acct_data[k]

            self._save_raw(data)
            logger.info("Switched active Antigravity account to: %s", target)
            return True

    def _score_account(self, acc: AntigravityAccount, model: str = "") -> float:
        """Helper to compute account routing health score with live in-flight count."""
        return acc.compute_routing_health_score(model, in_flight=self.get_in_flight_count(acc.email))

    def get_account_for_service(
        self,
        service_type: str = "all",  # 'llm', 'image_gen', 'all'
        exclude_emails: Optional[Set[str]] = None,
        model: str = "",
    ) -> Optional[AntigravityAccount]:
        """Select optimal account tailored for service type and model family with Quota-Aware Routing.
        Strictly enforces cooldown, model-family availability, and soft high-water mark (10%).
        """
        exclude = {e.lower().strip() for e in (exclude_emails or set())}
        accounts = [a for a in self.list_accounts() if a.email not in exclude]
        if not accounts:
            return None

        strategy = self.get_rotation_strategy()

        ready_accounts = [a for a in accounts if a.is_available_for_model(model)]
        if not ready_accounts:
            return None

        # Soft High-Water Mark: prefer accounts with > 10% remaining quota for target model family
        healthy_accounts = [
            a for a in ready_accounts
            if a.get_remaining_quota_pct(model) > SOFT_QUOTA_HIGH_WATER_MARK_PCT
        ]
        candidate_pool = healthy_accounts if healthy_accounts else ready_accounts

        if strategy == "sharded":
            if service_type in {"llm", "image_gen"}:
                role_matched = [a for a in candidate_pool if a.assigned_role == service_type]
                if role_matched:
                    role_matched.sort(
                        key=lambda a: (-self._score_account(a, model), a.last_used or 0.0, a.email)
                    )
                    return role_matched[0]

                all_role = [a for a in candidate_pool if a.assigned_role == "all"]
                if all_role:
                    all_role.sort(
                        key=lambda a: (-self._score_account(a, model), a.last_used or 0.0, a.email)
                    )
                    return all_role[0]

            candidate_pool.sort(
                key=lambda a: (-self._score_account(a, model), a.last_used or 0.0, a.email)
            )
            return candidate_pool[0]

        elif strategy == "round_robin":
            candidate_pool.sort(
                key=lambda a: (self.get_in_flight_count(a.email), a.last_used or 0.0, -self._score_account(a, model))
            )
            chosen = candidate_pool[0]
            self.set_active_account(chosen.email)
            return chosen

        elif strategy == "least_used":
            candidate_pool.sort(
                key=lambda a: (
                    self.get_in_flight_count(a.email),
                    a.total_requests,
                    -self._score_account(a, model),
                    a.last_used or 0.0,
                )
            )
            chosen = candidate_pool[0]
            self.set_active_account(chosen.email)
            return chosen

        else:  # 'fill_first' or 'failover'
            active = self.get_active_account()
            if (
                active
                and active.email not in exclude
                and active.is_available_for_model(model)
                and (not healthy_accounts or active.get_remaining_quota_pct(model) > SOFT_QUOTA_HIGH_WATER_MARK_PCT)
            ):
                return active

            candidate_pool.sort(
                key=lambda a: (-self._score_account(a, model), a.last_used or 0.0, a.email)
            )
            chosen = candidate_pool[0]
            self.set_active_account(chosen.email)
            return chosen

    def get_next_available_account(
        self,
        exclude_emails: Optional[Set[str]] = None,
        model: str = "",
    ) -> Optional[AntigravityAccount]:
        """Select the next available account based on active strategy, model family, and quota health."""
        return self.get_account_for_service("all", exclude_emails=exclude_emails, model=model)

    def mark_account_disabled(
        self,
        email: str,
        reason: str = "TOS_VIOLATION",
    ) -> Optional[AntigravityAccount]:
        """Permanently disable an account in the pool (e.g. on HTTP 403 TOS_VIOLATION) and fail over."""
        target = email.strip().lower()
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if isinstance(raw_accs, dict) and target in raw_accs:
                raw_accs[target]["status"] = "disabled"
                raw_accs[target]["exhausted_until"] = None
                raw_accs[target]["failure_count"] = int(raw_accs[target].get("failure_count", 0)) + 1
                raw_accs[target]["disabled_reason"] = reason
                data["accounts"] = raw_accs
                self._save_raw(data)
                logger.error(
                    "Antigravity account '%s' has been permanently marked DISABLED in pool. Reason: %s",
                    target, reason,
                )

        next_acc = self.get_next_available_account(exclude_emails={target})
        if next_acc:
            self.set_active_account(next_acc.email)
            logger.info("Auto-failover after disable: switched active account to '%s'", next_acc.email)
            return next_acc
        return None

    def mark_account_exhausted(
        self,
        email: str,
        cooldown_seconds: Optional[float] = None,
        reason: str = "",
        model: str = "",
        retry_after: Optional[float] = None,
    ) -> Optional[AntigravityAccount]:
        """Mark an account exhausted/cooling_down with Retry-After/tiered cooldown and model-family isolation."""
        target = email.strip().lower()
        if "tos_violation" in reason.lower() or "disabled in this account" in reason.lower():
            return self.mark_account_disabled(target, reason=reason)

        if cooldown_seconds is None:
            if retry_after is not None and retry_after > 0:
                cooldown_seconds = float(retry_after)
            else:
                parsed_retry = parse_retry_after_seconds(reason)
                if parsed_retry is not None and parsed_retry > 0:
                    cooldown_seconds = parsed_retry
                else:
                    cooldown_seconds = self.calculate_tiered_cooldown(target)

        now = time.time()
        cooldown_until = now + cooldown_seconds
        family = resolve_model_family(model)

        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if isinstance(raw_accs, dict) and target in raw_accs:
                if raw_accs[target].get("status") == "disabled":
                    return self.get_next_available_account(exclude_emails={target}, model=model)
                raw_accs[target]["status"] = "cooling_down"
                raw_accs[target]["exhausted_until"] = cooldown_until
                raw_accs[target]["failure_count"] = int(raw_accs[target].get("failure_count", 0)) + 1
                raw_accs[target]["consecutive_429_count"] = int(raw_accs[target].get("consecutive_429_count", 0)) + 1
                if family in {"claude", "gemini"}:
                    mc = raw_accs[target].get("model_cooldowns")
                    if not isinstance(mc, dict):
                        mc = {}
                    mc[family] = cooldown_until
                    raw_accs[target]["model_cooldowns"] = mc
                consec = raw_accs[target]["consecutive_429_count"]
                data["accounts"] = raw_accs
                self._save_raw(data)
                logger.warning(
                    "Antigravity account '%s' entered cooldown for %.0fs (family=%s, consecutive_429=%d, until %.0f). Reason: %s",
                    target, cooldown_seconds, family, consec, cooldown_until, reason or "Rate limit / Quota reached"
                )

        # Automatically switch to next available account
        next_acc = self.get_next_available_account(exclude_emails={target}, model=model)
        if next_acc:
            self.set_active_account(next_acc.email)
            logger.info("Auto-failover: switched active account to '%s'", next_acc.email)
            return next_acc

        return None

    def record_account_usage(self, email: str, success: bool = True, model: str = "") -> None:
        """Update last_used timestamp, micro-spacing timestamp, and request statistics."""
        target = email.strip().lower()
        now = time.time()
        family = resolve_model_family(model)
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
                    mc = acct.get("model_cooldowns")
                    if isinstance(mc, dict) and family in mc:
                        mc.pop(family, None)
                        acct["model_cooldowns"] = mc
                    if not acct.get("model_cooldowns"):
                        acct["status"] = "active"
                        acct["exhausted_until"] = None
                    acct["failure_count"] = 0
                    acct["consecutive_429_count"] = 0
                else:
                    acct["failure_count"] = int(acct.get("failure_count", 0)) + 1
                data["accounts"] = raw_accs
                self._save_raw(data)

    def add_or_update_account(self, creds: Any, reset_status: bool = False) -> AntigravityAccount:
        """Register or update an account from AntigravityCredentials or dict, preserving cooldown/disabled state."""
        if hasattr(creds, "email"):
            em = (creds.email or "primary").strip().lower()
            tier_id = getattr(creds, "tier_id", "") or ""
            p_name = getattr(creds, "plan_name", "") or ""
            p_type = getattr(creds, "plan_type", "") or ""
            p_low = p_name.lower()
            t_low = tier_id.lower()
            if "ultra" in p_low or "ultra" in t_low:
                p_type = "ultra"
                p_name = p_name or "Google AI Ultra"
            elif "pro" in p_low or "pro" in t_low:
                p_type = "pro"
                p_name = p_name or "Google AI Pro"
            elif p_type in {"ultra", "pro"}:
                p_name = p_name or ("Google AI Ultra" if p_type == "ultra" else "Google AI Pro")
            else:
                p_type = "free"
                p_name = p_name or "Free Tier"

            acc = AntigravityAccount(
                email=em,
                access_token=getattr(creds, "access_token", ""),
                refresh_token=getattr(creds, "refresh_token", ""),
                expires_at=getattr(creds, "expires_at", 0.0),
                project_id=getattr(creds, "project_id", "aicode-consumers") or "aicode-consumers",
                managed_project_id=getattr(creds, "managed_project_id", ""),
                tier_id=tier_id,
                source=getattr(creds, "source", "oauth_pkce"),
                status="active",
                plan_name=p_name,
                plan_type=p_type,
                quota_summary=dict(getattr(creds, "quota_summary", {}) or {}),
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

            # Preserve tokens, counters, and cooldown/disabled state if account already existed
            if acc.email in raw_accs:
                old = raw_accs[acc.email]
                if not acc.access_token and old.get("access_token"):
                    acc.access_token = old["access_token"]
                if not acc.refresh_token and old.get("refresh_token"):
                    acc.refresh_token = old["refresh_token"]
                if acc.expires_at <= 0 and old.get("expires_at"):
                    acc.expires_at = float(old["expires_at"])
                if not acc.managed_project_id and old.get("managed_project_id"):
                    acc.managed_project_id = old["managed_project_id"]
                if not acc.tier_id and old.get("tier_id"):
                    acc.tier_id = old["tier_id"]
                if not acc.plan_name or acc.plan_name.lower() in {"free", "free tier"}:
                    if old.get("plan_name") and old["plan_name"].lower() not in {"free", "free tier"}:
                        acc.plan_name = old["plan_name"]
                if (not acc.plan_type or acc.plan_type == "free") and old.get("plan_type") in {"pro", "ultra"}:
                    acc.plan_type = old["plan_type"]
                if not acc.quota_summary and old.get("quota_summary"):
                    acc.quota_summary = old["quota_summary"]

                # Re-check tier_id and plan_name after merge with old
                t_check = (acc.tier_id or "").lower()
                n_check = (acc.plan_name or "").lower()
                if "ultra" in t_check or "ultra" in n_check:
                    acc.plan_type = "ultra"
                    if not acc.plan_name or acc.plan_name.lower() in {"free", "free tier"}:
                        acc.plan_name = "Google AI Ultra"
                elif "pro" in t_check or "pro" in n_check:
                    acc.plan_type = "pro"
                    if not acc.plan_name or acc.plan_name.lower() in {"free", "free tier"}:
                        acc.plan_name = "Google AI Pro"

                if not acc.project_id or acc.project_id == "aicode-consumers":
                    if acc.managed_project_id and acc.managed_project_id != "aicode-consumers":
                        acc.project_id = acc.managed_project_id
                    elif old.get("project_id"):
                        acc.project_id = old["project_id"]
                acc.total_requests = int(old.get("total_requests", 0))
                acc.last_used = old.get("last_used")
                acc.last_request_time = float(old.get("last_request_time", 0.0) or 0.0)
                acc.assigned_role = str(old.get("assigned_role", acc.assigned_role or "all"))
                if not reset_status:
                    if not acc.model_cooldowns and isinstance(old.get("model_cooldowns"), dict):
                        acc.model_cooldowns = {
                            str(k).strip().lower(): float(v)
                            for k, v in old["model_cooldowns"].items()
                            if v is not None
                        }
                    old_status = str(old.get("status", "active"))
                    if old_status in {"cooling_down", "exhausted", "disabled"}:
                        acc.status = old_status
                        acc.exhausted_until = float(old["exhausted_until"]) if old.get("exhausted_until") else None
                        acc.consecutive_429_count = int(old.get("consecutive_429_count", 0))
                        acc.failure_count = int(old.get("failure_count", 0))

            raw_accs[acc.email] = acc.to_dict()
            data["accounts"] = raw_accs

            # If no active account, make this one active
            if not data.get("active_account_email"):
                data["active_account_email"] = acc.email

            # Sync root keys if active
            if data.get("active_account_email") == acc.email:
                for k, v in acc.to_dict().items():
                    if k in {
                        "access_token", "refresh_token", "expires_at", "email",
                        "project_id", "managed_project_id", "tier_id", "source",
                        "plan_name", "plan_type", "quota_summary"
                    }:
                        data[k] = v

            self._save_raw(data)
            logger.info("Saved account '%s' to Antigravity account pool (status=%s, plan=%s).", acc.email, acc.status, acc.plan_name or "free")
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
            if self.storage_path == DEFAULT_TOKENS_FILE:
                mirror_files: List[Path] = []
                try:
                    dot_hermes = Path.home() / ".hermes"
                    mirror_files.append(dot_hermes / "auth" / "antigravity_tokens.json")
                    dot_profiles = dot_hermes / "profiles"
                    if dot_profiles.is_dir():
                        for p in sorted(dot_profiles.iterdir()):
                            if p.is_dir() and not p.name.startswith("."):
                                mirror_files.append(p / "auth" / "antigravity_tokens.json")
                    if os.name == "nt":
                        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
                        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
                        appdata_h = base / "hermes"
                        mirror_files.append(appdata_h / "auth" / "antigravity_tokens.json")
                        win_profiles = appdata_h / "profiles"
                        if win_profiles.is_dir():
                            for p in sorted(win_profiles.iterdir()):
                                if p.is_dir() and not p.name.startswith("."):
                                    mirror_files.append(p / "auth" / "antigravity_tokens.json")
                except Exception:
                    pass
                for mf in mirror_files:
                    try:
                        if mf.resolve() == self.storage_path.resolve() or not mf.is_file():
                            continue
                        with open(mf, "r", encoding="utf-8") as f:
                            mdata = json.load(f)
                        maccs = mdata.get("accounts")
                        if isinstance(maccs, dict) and target in maccs:
                            del maccs[target]
                            mdata["accounts"] = maccs
                            tmp_m = mf.with_name(f"{mf.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                            with open(tmp_m, "w", encoding="utf-8") as f:
                                json.dump(mdata, f, indent=2)
                            os.replace(str(tmp_m), str(mf))
                    except Exception:
                        pass
            logger.info("Removed account '%s' from Antigravity account pool.", target)
            return True

    def refresh_account_plan_and_quota(self, email: str) -> Dict[str, Any]:
        """Fetch live Plan name (Ultra/Pro/Free) and Quota telemetry for an account from Google Code Assist."""
        target = (email or "").strip().lower()
        if not target:
            return {"ok": False, "email": "", "message": "Email tài khoản không hợp lệ."}

        acc = self.get_account(target)
        if not acc:
            return {"ok": False, "email": target, "message": f"Không tìm thấy tài khoản '{target}' trong pool."}

        try:
            from bridge.auth import (
                AntigravityAuthManager,
                AntigravityCredentials,
                LOAD_CODE_ASSIST_ENDPOINT,
                FALLBACK_LOAD_CODE_ASSIST_ENDPOINT,
            )
            from bridge.fingerprint import AntigravityFingerprint
            from bridge.models import QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT
        except ImportError:
            from tools.antigravity_bridge.auth import (
                AntigravityAuthManager,
                AntigravityCredentials,
                LOAD_CODE_ASSIST_ENDPOINT,
                FALLBACK_LOAD_CODE_ASSIST_ENDPOINT,
            )
            from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
            from tools.antigravity_bridge.models import QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT

        auth_mgr = AntigravityAuthManager(auth_file=self.storage_path)
        creds = AntigravityCredentials(
            access_token=acc.access_token,
            refresh_token=acc.refresh_token,
            expires_at=acc.expires_at,
            email=acc.email,
            project_id=acc.project_id,
            managed_project_id=acc.managed_project_id,
            tier_id=acc.tier_id,
            source=acc.source,
            plan_name=acc.plan_name,
        )

        if creds.is_expired and creds.refresh_token:
            try:
                creds = auth_mgr.refresh_access_token(creds)
                acc.access_token = creds.access_token
                acc.expires_at = creds.expires_at
            except Exception as e:
                logger.warning("Token refresh failed during plan check for %s: %s", target, e)
                return {
                    "ok": False,
                    "email": target,
                    "plan_name": acc.plan_name or "Free Tier",
                    "plan_type": acc.computed_plan_type,
                    "quota_summary": acc.quota_summary,
                    "message": f"Không thể làm mới token cho {target}: {e}",
                }

        import urllib.request
        import urllib.error
        import gzip

        headers = AntigravityFingerprint.build_headers(creds.access_token)
        metadata = AntigravityFingerprint.build_client_metadata()

        plan_name = acc.plan_name or "Free Tier"
        plan_type = acc.computed_plan_type
        pid = acc.effective_project_id

        # 1. Query loadCodeAssist
        try:
            load_body = json.dumps({"metadata": metadata}).encode("utf-8")
            data: Dict[str, Any] = {}
            for ep in (LOAD_CODE_ASSIST_ENDPOINT, FALLBACK_LOAD_CODE_ASSIST_ENDPOINT):
                try:
                    req = urllib.request.Request(ep, data=load_body, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        raw = resp.read()
                        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                            raw = gzip.decompress(raw)
                        data = json.loads(raw.decode("utf-8"))
                    break
                except urllib.error.HTTPError as he:
                    if he.code in {404, 500, 502, 503, 504} and ep == LOAD_CODE_ASSIST_ENDPOINT:
                        continue
                    raise

            if data:
                paid_tier = data.get("paidTier")
                current_tier = data.get("currentTier")
                if isinstance(paid_tier, dict) and paid_tier.get("name"):
                    p_name = str(paid_tier.get("name") or "")
                    p_id = str(paid_tier.get("id") or "").lower()
                    if "ultra" in p_name.lower() or "ultra" in p_id:
                        plan_type = "ultra"
                        plan_name = p_name or "Google AI Ultra"
                    elif "pro" in p_name.lower() or "pro" in p_id:
                        plan_type = "pro"
                        plan_name = p_name or "Google AI Pro"
                    elif "free" in p_id or "free" in p_name.lower() or "starter" in p_name.lower():
                        plan_type = "free"
                        plan_name = "Free Tier"
                    else:
                        plan_type = "free"
                        plan_name = p_name or "Free Tier"
                elif isinstance(current_tier, dict):
                    c_name = str(current_tier.get("name") or "")
                    c_id = str(current_tier.get("id") or "").lower()
                    if "ultra" in c_name.lower() or "ultra" in c_id:
                        plan_type = "ultra"
                        plan_name = c_name or "Google AI Ultra"
                    elif "pro" in c_name.lower() or "pro" in c_id:
                        plan_type = "pro"
                        plan_name = c_name or "Google AI Pro"
                    else:
                        plan_type = "free"
                        plan_name = "Free Tier" if ("free" in c_id or "antigravity" in c_name.lower()) else (c_name or "Free Tier")
                else:
                    plan_type = "free"
                    plan_name = "Free Tier"

                extracted_pid = auth_mgr._extract_companion_project_id(data)
                if extracted_pid:
                    pid = extracted_pid
        except Exception as e:
            logger.debug("loadCodeAssist failed for %s during plan refresh: %s", target, e)

        # 2. Query retrieveUserQuotaSummary
        quota_summary = dict(acc.quota_summary or {})
        try:
            q_headers = AntigravityFingerprint.build_headers(creds.access_token, project_id=pid)
            q_body = json.dumps({"project": pid}).encode("utf-8")
            q_data: Dict[str, Any] = {}
            for ep in (QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT):
                try:
                    q_req = urllib.request.Request(ep, data=q_body, headers=q_headers, method="POST")
                    with urllib.request.urlopen(q_req, timeout=10.0) as resp:
                        raw = resp.read()
                        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                            raw = gzip.decompress(raw)
                        q_data = json.loads(raw.decode("utf-8"))
                    break
                except urllib.error.HTTPError as he:
                    if he.code in {404, 500, 502, 503, 504} and ep == QUOTA_ENDPOINT:
                        continue
                    raise

            if q_data and isinstance(q_data.get("groups"), list):
                for g in q_data["groups"]:
                    if not isinstance(g, dict):
                        continue
                    g_name = (g.get("displayName") or "").lower()
                    buckets = g.get("buckets") or g.get("quotaBuckets") or []
                    for b in buckets:
                        if not isinstance(b, dict):
                            continue
                        bid = str(b.get("bucketId") or b.get("bucket") or b.get("id") or "").lower()
                        rf = b.get("remainingFraction")
                        pct = round(float(rf) * 100) if rf is not None else None
                        rt = b.get("resetTime")
                        if "gemini" in g_name or "gemini" in bid:
                            if "weekly" in bid:
                                quota_summary["gemini_weekly_pct"] = pct
                                if rt:
                                    quota_summary["gemini_reset_time"] = rt
                            elif "5h" in bid:
                                quota_summary["gemini_5h_pct"] = pct
                        elif "claude" in g_name or "gpt" in g_name or "3p" in bid or "claude" in bid:
                            if "weekly" in bid:
                                quota_summary["claude_weekly_pct"] = pct
                                if rt:
                                    quota_summary["claude_reset_time"] = rt
                            elif "5h" in bid:
                                quota_summary["claude_5h_pct"] = pct
        except Exception as e:
            logger.debug("retrieveUserQuotaSummary failed for %s during quota refresh: %s", target, e)

        # 3. Save to account and persist
        with self._lock:
            data = self._load_raw()
            raw_accs = data.get("accounts", {})
            if isinstance(raw_accs, dict) and target in raw_accs:
                raw_accs[target]["plan_name"] = plan_name
                raw_accs[target]["plan_type"] = plan_type
                raw_accs[target]["quota_summary"] = quota_summary
                if pid and pid != "aicode-consumers":
                    raw_accs[target]["managed_project_id"] = pid
                    raw_accs[target]["project_id"] = pid
                data["accounts"] = raw_accs

                if data.get("active_account_email") == target:
                    data["plan_name"] = plan_name
                    data["plan_type"] = plan_type
                    data["quota_summary"] = quota_summary

                self._save_raw(data)

        return {
            "ok": True,
            "email": target,
            "plan_name": plan_name,
            "plan_type": plan_type,
            "quota_summary": quota_summary,
            "message": f"Đã cập nhật gói {plan_name} ({plan_type.upper()}) và hạn mức quota cho {target}.",
        }

    def _synthesize_quota_groups(self, acc: AntigravityAccount) -> Dict[str, Any]:
        """Synthesize groups/buckets structure from stored quota_summary."""
        qs = acc.quota_summary or {}
        g_pct = qs.get("gemini_weekly_pct")
        c_pct = qs.get("claude_weekly_pct")
        groups = []
        if g_pct is not None:
            g_b = [{
                "bucketId": "gemini_weekly",
                "displayName": "Weekly Limit Remaining",
                "remainingFraction": float(g_pct) / 100.0,
            }]
            g_5h = qs.get("gemini_5h_pct")
            if g_5h is not None:
                g_b.append({
                    "bucketId": "gemini_5h",
                    "displayName": "Five Hour Limit Remaining",
                    "remainingFraction": float(g_5h) / 100.0,
                })
            groups.append({
                "displayName": "Gemini Models",
                "buckets": g_b,
            })
        if c_pct is not None:
            c_b = [{
                "bucketId": "claude_weekly",
                "displayName": "Weekly Limit Remaining",
                "remainingFraction": float(c_pct) / 100.0,
            }]
            c_5h = qs.get("claude_5h_pct")
            if c_5h is not None:
                c_b.append({
                    "bucketId": "claude_5h",
                    "displayName": "Five Hour Limit Remaining",
                    "remainingFraction": float(c_5h) / 100.0,
                })
            groups.append({
                "displayName": "Claude and GPT models",
                "buckets": c_b,
            })
        return {"groups": groups}

    def get_account_quota_buckets(self, email: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Query live retrieveUserQuotaSummary buckets for a specific account or fallback to synthesized groups."""
        target = (email or "").strip().lower()
        if not target or target == "active":
            acc = self.get_active_account()
            if not acc:
                return {}
            target = acc.email

        acc = self.get_account(target)
        if not acc:
            return {}

        try:
            try:
                from tools.antigravity_bridge.auth import AntigravityAuthManager, AntigravityCredentials
                from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
                from tools.antigravity_bridge.models import QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT
            except ImportError:
                from bridge.auth import AntigravityAuthManager, AntigravityCredentials
                from bridge.fingerprint import AntigravityFingerprint
                from bridge.models import QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT

            auth_mgr = AntigravityAuthManager(auth_file=self.storage_path)
            creds = AntigravityCredentials(
                access_token=acc.access_token,
                refresh_token=acc.refresh_token,
                expires_at=acc.expires_at,
                email=acc.email,
                project_id=acc.project_id,
                managed_project_id=acc.managed_project_id,
                tier_id=acc.tier_id,
                source=acc.source,
                plan_name=acc.plan_name,
                plan_type=acc.computed_plan_type,
            )
            if creds.is_expired and creds.refresh_token:
                try:
                    creds = auth_mgr.refresh_access_token(creds)
                    acc.access_token = creds.access_token
                    acc.expires_at = creds.expires_at
                except Exception as e:
                    logger.warning("Token refresh failed during quota fetch for %s: %s", target, e)

            pid = acc.effective_project_id
            headers = AntigravityFingerprint.build_headers(creds.access_token, project_id=pid)
            body = json.dumps({"project": pid}).encode("utf-8")

            import urllib.request
            import urllib.error
            import gzip

            q_data: Dict[str, Any] = {}
            for ep in (QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT):
                try:
                    req = urllib.request.Request(ep, data=body, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        raw = resp.read()
                        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                            raw = gzip.decompress(raw)
                        q_data = json.loads(raw.decode("utf-8"))
                    break
                except urllib.error.HTTPError as he:
                    if he.code in {404, 500, 502, 503, 504} and ep == QUOTA_ENDPOINT:
                        continue
                    raise

            if q_data and isinstance(q_data.get("groups"), list) and q_data["groups"]:
                quota_summary = dict(acc.quota_summary or {})
                for g in q_data["groups"]:
                    if not isinstance(g, dict):
                        continue
                    g_name = (g.get("displayName") or "").lower()
                    buckets = g.get("buckets") or g.get("quotaBuckets") or []
                    for b in buckets:
                        if not isinstance(b, dict):
                            continue
                        bid = str(b.get("bucketId") or b.get("bucket") or b.get("id") or "").lower()
                        rf = b.get("remainingFraction")
                        pct = round(float(rf) * 100) if rf is not None else None
                        rt = b.get("resetTime")
                        if "gemini" in g_name or "gemini" in bid:
                            if "weekly" in bid:
                                quota_summary["gemini_weekly_pct"] = pct
                                if rt:
                                    quota_summary["gemini_reset_time"] = rt
                            elif "5h" in bid:
                                quota_summary["gemini_5h_pct"] = pct
                        elif "claude" in g_name or "gpt" in g_name or "3p" in bid or "claude" in bid:
                            if "weekly" in bid:
                                quota_summary["claude_weekly_pct"] = pct
                                if rt:
                                    quota_summary["claude_reset_time"] = rt
                            elif "5h" in bid:
                                quota_summary["claude_5h_pct"] = pct

                with self._lock:
                    data = self._load_raw()
                    raw_accs = data.get("accounts", {})
                    if isinstance(raw_accs, dict) and target in raw_accs:
                        raw_accs[target]["quota_summary"] = quota_summary
                        data["accounts"] = raw_accs
                        if data.get("active_account_email") == target:
                            data["quota_summary"] = quota_summary
                        self._save_raw(data)

                return q_data
        except Exception as e:
            logger.debug("Live get_account_quota_buckets failed for %s: %s", target, e)

        # Fallback to synthesized groups from cached quota_summary
        if acc.quota_summary:
            return self._synthesize_quota_groups(acc)
        return {}
