"""Antigravity OAuth authentication & token management for Local Bridge.

Handles:
- Discovering existing Antigravity tokens from local CLI/IDE configurations.
- Google OAuth 2.0 PKCE flow (browser auth).
- Persistent token storage in ~/.hermes/auth/antigravity_tokens.json with auto-refresh and multi-account support.
- Google Cloud Project ID resolution for Code Assist backend.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import json
import logging
import os
import re
import secrets
import shutil
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Constants
ENV_CLIENT_ID = "HERMES_ANTIGRAVITY_CLIENT_ID"
ENV_CLIENT_SECRET = "HERMES_ANTIGRAVITY_CLIENT_SECRET"
ENV_PROJECT_ID = "HERMES_ANTIGRAVITY_PROJECT_ID"
ENV_CLI_PATH = "HERMES_ANTIGRAVITY_CLI_PATH"

_PUBLIC_CLIENT_ID_PROJECT_NUM = "1071006060591"
_PUBLIC_CLIENT_ID_HASH = "tmhssin2h21lcre235vtolojh4g403ep"
_PUBLIC_CLIENT_SECRET_SUFFIX = "K58FWR486LdLJ1mLB8sXC4z6qDAf"

DEFAULT_CLIENT_ID = (
    f"{_PUBLIC_CLIENT_ID_PROJECT_NUM}-{_PUBLIC_CLIENT_ID_HASH}.apps.googleusercontent.com"
)
DEFAULT_CLIENT_SECRET = f"GOCSPX-{_PUBLIC_CLIENT_SECRET_SUFFIX}"
DEFAULT_PROJECT_ID = "aicode-consumers"

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"
LOAD_CODE_ASSIST_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
FALLBACK_LOAD_CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
ONBOARD_USER_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:onboardUser"
FALLBACK_ONBOARD_USER_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:onboardUser"

OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs"
)

DEFAULT_REDIRECT_PORT = 51121
REDIRECT_HOST = "localhost"
CALLBACK_PATH = "/oauth-callback"
REFRESH_SKEW_SECONDS = 120
LOCK_TIMEOUT_SECONDS = 15.0


def get_hermes_dir() -> Path:
    """Return platform-aware Hermes home directory."""
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except Exception:
        custom = os.getenv("HERMES_HOME")
        if custom:
            return Path(custom).expanduser()
        if sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
            base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
            return base / "hermes"
        return Path.home() / ".hermes"


@dataclass
class AntigravityCredentials:
    """Container for Antigravity OAuth tokens and metadata."""
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0
    email: str = ""
    project_id: str = ""
    managed_project_id: str = ""
    tier_id: str = ""
    source: str = "oauth_pkce"
    plan_name: str = ""
    plan_type: str = ""
    quota_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def effective_project_id(self) -> str:
        """Return the Google-assigned managed companion project ID first, falling back to project_id."""
        if self.managed_project_id and self.managed_project_id != DEFAULT_PROJECT_ID:
            return self.managed_project_id
        if self.project_id and self.project_id != DEFAULT_PROJECT_ID:
            return self.project_id
        return self.managed_project_id or self.project_id or DEFAULT_PROJECT_ID

    @property
    def is_expired(self) -> bool:
        """True if the access token has expired or is within the refresh window."""
        if not self.access_token:
            return True
        if self.expires_at <= 0:
            return False
        return (self.expires_at - time.time()) < REFRESH_SKEW_SECONDS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "email": self.email,
            "project_id": self.project_id,
            "managed_project_id": self.managed_project_id,
            "tier_id": self.tier_id,
            "source": self.source,
            "plan_name": self.plan_name,
            "plan_type": self.plan_type,
            "quota_summary": self.quota_summary,
            "updated_at": time.time(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AntigravityCredentials:
        return cls(
            access_token=data.get("access_token") or "",
            refresh_token=data.get("refresh_token") or "",
            expires_at=float(data.get("expires_at") or 0.0),
            email=data.get("email") or "",
            project_id=data.get("project_id") or "",
            managed_project_id=data.get("managed_project_id") or "",
            tier_id=data.get("tier_id") or "",
            source=data.get("source") or "oauth_pkce",
            plan_name=data.get("plan_name") or "",
            plan_type=data.get("plan_type") or "",
            quota_summary=dict(data.get("quota_summary") or {}) if isinstance(data.get("quota_summary"), dict) else {},
        )


class AntigravityAuthManager:
    """Manages token resolution, storage, and PKCE login for Antigravity."""

    def __init__(self, auth_file: Optional[Path] = None) -> None:
        self._auth_file_is_custom = auth_file is not None
        self.auth_file = auth_file or (get_hermes_dir() / "auth" / "antigravity_tokens.json")
        self._lock = threading.Lock()
        self._resolved_project_cache: Dict[str, str] = {}

    @property
    def token_file(self) -> Path:
        """Alias for auth_file."""
        return self.auth_file

    def get_client_id(self) -> str:
        """Get the OAuth client ID from env or public default."""
        return (os.getenv(ENV_CLIENT_ID) or "").strip() or DEFAULT_CLIENT_ID

    def get_client_secret(self) -> str:
        """Get the OAuth client secret from env or public default."""
        return (os.getenv(ENV_CLIENT_SECRET) or "").strip() or DEFAULT_CLIENT_SECRET

    def load_all_stored_credentials(self) -> List[AntigravityCredentials]:
        """Load all stored credentials (multi-account) from auth file."""
        candidate_files = [self.auth_file]
        if not self._auth_file_is_custom:
            try:
                dot_hermes = Path.home() / ".hermes"
                root_home = dot_hermes / "auth" / "antigravity_tokens.json"
                if root_home not in candidate_files and root_home.is_file():
                    candidate_files.append(root_home)
                dot_profiles = dot_hermes / "profiles"
                if dot_profiles.is_dir():
                    for p in sorted(dot_profiles.iterdir()):
                        if p.is_dir() and not p.name.startswith("."):
                            pf = p / "auth" / "antigravity_tokens.json"
                            if pf not in candidate_files and pf.is_file():
                                candidate_files.append(pf)
                if sys.platform == "win32":
                    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
                    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
                    root_appdata = base / "hermes" / "auth" / "antigravity_tokens.json"
                    if root_appdata not in candidate_files and root_appdata.is_file():
                        candidate_files.append(root_appdata)
                    win_profiles = base / "hermes" / "profiles"
                    if win_profiles.is_dir():
                        for p in sorted(win_profiles.iterdir()):
                            if p.is_dir() and not p.name.startswith("."):
                                pf = p / "auth" / "antigravity_tokens.json"
                                if pf not in candidate_files and pf.is_file():
                                    candidate_files.append(pf)
            except Exception:
                pass
        creds_list: List[AntigravityCredentials] = []
        seen_emails: set[str] = set()

        for cpath in candidate_files:
            if not cpath.is_file():
                continue
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    accounts = data.get("accounts")
                    if isinstance(accounts, dict):
                        for email_key, acct_data in accounts.items():
                            if isinstance(acct_data, dict) and acct_data.get("access_token"):
                                em = (acct_data.get("email") or email_key).strip().lower()
                                if em not in seen_emails:
                                    seen_emails.add(em)
                                    creds_list.append(AntigravityCredentials.from_dict(acct_data))
                    elif isinstance(accounts, list):
                        for acct_data in accounts:
                            if isinstance(acct_data, dict) and acct_data.get("access_token"):
                                em = (acct_data.get("email") or "primary").strip().lower()
                                if em not in seen_emails:
                                    seen_emails.add(em)
                                    creds_list.append(AntigravityCredentials.from_dict(acct_data))
                    if data.get("access_token"):
                        em = (data.get("email") or "primary").strip().lower()
                        if em not in seen_emails:
                            seen_emails.add(em)
                            creds_list.append(AntigravityCredentials.from_dict(data))
            except Exception as e:
                logger.warning("Failed to read credentials from %s: %s", cpath, e)

        return creds_list

    def load_stored_credentials(self, email: Optional[str] = None) -> Optional[AntigravityCredentials]:
        """Load credentials from ~/.hermes/auth/antigravity_tokens.json respecting active account."""
        all_creds = self.load_all_stored_credentials()
        if not all_creds:
            return None
        if email:
            for c in all_creds:
                if c.email.lower() == email.lower():
                    return c

        try:
            if self.auth_file.is_file():
                with open(self.auth_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                active_em = (raw_data.get("active_account_email") or "").strip().lower()
                if active_em:
                    for c in all_creds:
                        if c.email.lower() == active_em:
                            return c
        except Exception:
            pass

        return all_creds[0]

    def save_credentials(self, creds: AntigravityCredentials, reset_status: bool = False) -> None:
        """Save credentials atomically preserving all accounts and syncing to all profile auth stores."""
        target_token_files = [self.auth_file]
        if not self._auth_file_is_custom:
            try:
                dot_hermes = Path.home() / ".hermes"
                target_token_files.append(dot_hermes / "auth" / "antigravity_tokens.json")
                dot_profiles = dot_hermes / "profiles"
                if dot_profiles.is_dir():
                    for p in sorted(dot_profiles.iterdir()):
                        if p.is_dir() and not p.name.startswith("."):
                            target_token_files.append(p / "auth" / "antigravity_tokens.json")
                if sys.platform == "win32":
                    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
                    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
                    appdata_hermes = base / "hermes"
                    target_token_files.append(appdata_hermes / "auth" / "antigravity_tokens.json")
                    profiles_dir = appdata_hermes / "profiles"
                    if profiles_dir.is_dir():
                        for p in sorted(profiles_dir.iterdir()):
                            if p.is_dir() and not p.name.startswith("."):
                                target_token_files.append(p / "auth" / "antigravity_tokens.json")
            except Exception:
                pass
        # Deduplicate
        seen_targets = set()
        dedup_targets = []
        for tf in target_token_files:
            try:
                key = str(tf.resolve())
            except Exception:
                key = str(tf)
            if key not in seen_targets:
                seen_targets.add(key)
                dedup_targets.append(tf)
        target_token_files = dedup_targets
        tmp_path: Optional[Path] = None
        try:
            existing_data: Dict[str, Any] = {}
            merged_accounts: Dict[str, Dict[str, Any]] = {}
            for tf in target_token_files:
                if not tf.is_file():
                    continue
                with contextlib.suppress(Exception):
                    with open(tf, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                    if not isinstance(file_data, dict):
                        continue
                    if not existing_data:
                        existing_data = dict(file_data)
                    raw_accs = file_data.get("accounts")
                    iter_items: List[Tuple[str, Dict[str, Any]]] = []
                    if isinstance(raw_accs, dict):
                        for k, v in raw_accs.items():
                            if isinstance(v, dict):
                                iter_items.append(((v.get("email") or k or "primary").strip().lower(), v))
                    elif isinstance(raw_accs, list):
                        for v in raw_accs:
                            if isinstance(v, dict) and (v.get("email") or v.get("access_token")):
                                iter_items.append(((v.get("email") or "primary").strip().lower(), v))
                    if file_data.get("access_token"):
                        top_em = (file_data.get("email") or "primary").strip().lower()
                        if top_em not in dict(iter_items):
                            top_copy = {k: v for k, v in file_data.items() if k != "accounts"}
                            iter_items.append((top_em, top_copy))
                    for em_k, acc_v in iter_items:
                        if not em_k:
                            continue
                        prev_m = merged_accounts.get(em_k)
                        if not prev_m:
                            merged_accounts[em_k] = dict(acc_v)
                        else:
                            # Merge keeping newer token fields while preserving non-empty metadata
                            prev_ts = float(prev_m.get("updated_at") or prev_m.get("expires_at") or 0.0)
                            curr_ts = float(acc_v.get("updated_at") or acc_v.get("expires_at") or 0.0)
                            is_curr_strictly_newer = curr_ts > prev_ts
                            base_acc = dict(prev_m) if is_curr_strictly_newer else dict(acc_v)
                            newer_acc = acc_v if is_curr_strictly_newer else prev_m
                            for mk, mv in newer_acc.items():
                                if mv not in (None, "", {}, []):
                                    base_acc[mk] = mv
                            # Preserve monotonic counters & timestamps across profile mirrors
                            base_acc["total_requests"] = max(
                                int(prev_m.get("total_requests", 0) or 0),
                                int(acc_v.get("total_requests", 0) or 0),
                            )
                            base_acc["failure_count"] = max(
                                int(prev_m.get("failure_count", 0) or 0),
                                int(acc_v.get("failure_count", 0) or 0),
                            )
                            max_lu = max(
                                float(prev_m.get("last_used") or 0.0),
                                float(acc_v.get("last_used") or 0.0),
                            )
                            if max_lu > 0:
                                base_acc["last_used"] = max_lu
                            max_lrt = max(
                                float(prev_m.get("last_request_time") or 0.0),
                                float(acc_v.get("last_request_time") or 0.0),
                            )
                            if max_lrt > 0:
                                base_acc["last_request_time"] = max_lrt
                            # Sticky disabled guard: never let a stale profile mirror resurrect a disabled account
                            if prev_m.get("status") == "disabled" or acc_v.get("status") == "disabled":
                                if not (reset_status and em_k == (creds.email or "primary").strip().lower()):
                                    base_acc["status"] = "disabled"
                                    base_acc["exhausted_until"] = None
                                    base_acc["disabled_reason"] = (
                                        prev_m.get("disabled_reason") or acc_v.get("disabled_reason") or "TOS_VIOLATION"
                                    )
                            merged_accounts[em_k] = base_acc

            accounts = merged_accounts

            email_key = (creds.email or "primary").strip().lower()
            prev_acct = accounts.get(email_key) if isinstance(accounts.get(email_key), dict) else {}
            new_acct = dict(prev_acct)
            for k, v in creds.to_dict().items():
                if k in {"managed_project_id", "tier_id", "plan_name", "plan_type", "quota_summary"} and not v and prev_acct.get(k):
                    continue
                if k == "project_id" and (not v or v == DEFAULT_PROJECT_ID) and prev_acct.get("managed_project_id"):
                    new_acct["project_id"] = prev_acct["managed_project_id"]
                    continue
                new_acct[k] = v
            tid = str(new_acct.get("tier_id", "") or "").lower()
            pname = str(new_acct.get("plan_name", "") or "")
            if "ultra" in tid or "ultra" in pname.lower():
                new_acct["plan_type"] = "ultra"
                if not pname or pname.lower() in {"free", "free tier"}:
                    new_acct["plan_name"] = "Google AI Ultra"
            elif "pro" in tid or "pro" in pname.lower():
                new_acct["plan_type"] = "pro"
                if not pname or pname.lower() in {"free", "free tier"}:
                    new_acct["plan_name"] = "Google AI Pro"
            if reset_status or "status" not in new_acct:
                new_acct["status"] = "active"
                new_acct["exhausted_until"] = None
                new_acct["consecutive_429_count"] = 0
            accounts[email_key] = new_acct

            out_data = dict(existing_data)
            for k, v in new_acct.items():
                out_data[k] = v
            out_data["accounts"] = accounts
            active_em_curr = str(out_data.get("active_account_email") or "").strip().lower()
            if not active_em_curr or reset_status or (
                isinstance(accounts.get(active_em_curr), dict)
                and accounts[active_em_curr].get("status") == "disabled"
            ):
                if new_acct.get("status") != "disabled":
                    out_data["active_account_email"] = email_key
                else:
                    healthy_em = next(
                        (ek for ek, ev in accounts.items() if isinstance(ev, dict) and ev.get("status") != "disabled"),
                        email_key,
                    )
                    out_data["active_account_email"] = healthy_em

            # Save token files using process+thread-unique temp path to avoid cross-process truncation races
            unique_suffix = f".{os.getpid()}.{threading.get_ident()}.tmp"
            for tf in target_token_files:
                try:
                    tf.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = tf.with_name(tf.name + unique_suffix)
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        json.dump(out_data, f, indent=2)
                    if os.name != "nt":
                        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
                    os.replace(str(tmp_path), str(tf))
                except Exception as e:
                    logger.debug("Failed saving token file to %s: %s", tf, e)
                    if tmp_path is not None and tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)

            # Build pool entries
            pool_entries = []
            for email_k, acct in accounts.items():
                exp_ms = int(float(acct.get("expires_at", 0)) * 1000) if acct.get("expires_at") else None
                pool_entries.append({
                    "id": hashlib.sha256(email_k.encode("utf-8")).hexdigest()[:6],
                    "source": f"oauth:{email_k}",
                    "auth_type": "oauth",
                    "access_token": acct.get("access_token") or "",
                    "refresh_token": acct.get("refresh_token") or "",
                    "expires_at_ms": exp_ms,
                    "base_url": "http://127.0.0.1:8100/v1",
                    "label": email_k,
                })

            provider_payload = {
                "access_token": creds.access_token,
                "refresh_token": creds.refresh_token,
                "email": creds.email,
                "project_id": creds.effective_project_id or creds.project_id,
                "expires_at": creds.expires_at,
                "updated_at": time.time(),
            }

            auth_store_targets = [get_hermes_dir() / "auth.json"]
            if not self._auth_file_is_custom:
                try:
                    dot_hermes = Path.home() / ".hermes"
                    auth_store_targets.append(dot_hermes / "auth.json")
                    dot_profiles = dot_hermes / "profiles"
                    if dot_profiles.is_dir():
                        for p in sorted(dot_profiles.iterdir()):
                            if p.is_dir() and not p.name.startswith("."):
                                auth_store_targets.append(p / "auth.json")
                    if sys.platform == "win32":
                        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
                        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
                        appdata_h = base / "hermes"
                        auth_store_targets.append(appdata_h / "auth.json")
                        p_dir = appdata_h / "profiles"
                        if p_dir.is_dir():
                            for p in sorted(p_dir.iterdir()):
                                if p.is_dir() and not p.name.startswith("."):
                                    auth_store_targets.append(p / "auth.json")
                except Exception:
                    pass
            # Deduplicate
            seen_ast = set()
            dedup_ast = []
            for at in auth_store_targets:
                try:
                    key = str(at.resolve())
                except Exception:
                    key = str(at)
                if key not in seen_ast:
                    seen_ast.add(key)
                    dedup_ast.append(at)
            auth_store_targets = dedup_ast

            for ast in auth_store_targets:
                tmp_ast: Optional[Path] = None
                try:
                    ast.parent.mkdir(parents=True, exist_ok=True)
                    store: Dict[str, Any] = {}
                    if ast.is_file():
                        with contextlib.suppress(Exception):
                            with open(ast, "r", encoding="utf-8") as af:
                                store = json.load(af)

                    store.setdefault("credential_pool", {})["antigravity"] = pool_entries
                    store.setdefault("providers", {})["antigravity"] = provider_payload

                    tmp_ast = ast.with_name(ast.name + unique_suffix)
                    with open(tmp_ast, "w", encoding="utf-8") as af:
                        json.dump(store, af, indent=2)
                    if os.name != "nt":
                        os.chmod(tmp_ast, stat.S_IRUSR | stat.S_IWUSR)
                    os.replace(str(tmp_ast), str(ast))
                except Exception as e:
                    logger.debug("Failed syncing auth store to %s: %s", ast, e)
                    if tmp_ast is not None and tmp_ast.exists():
                        tmp_ast.unlink(missing_ok=True)

            # Sync to AntigravityAccountPoolManager
            try:
                try:
                    from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
                except ImportError:
                    from bridge.account_pool import AntigravityAccountPoolManager
                pool = AntigravityAccountPoolManager(storage_path=self.auth_file)
                pool.add_or_update_account(creds)
            except Exception as e:
                logger.debug("Failed registering account to pool: %s", e)

        except Exception as e:
            logger.error("Failed to save credentials: %s", e)
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def clear_credentials(self) -> bool:
        """Remove stored credentials from ~/.hermes/auth/antigravity_tokens.json."""
        with self._lock:
            if self.auth_file.exists():
                try:
                    self.auth_file.unlink()
                    logger.info("Removed stored Antigravity credentials at %s", self.auth_file)
                    return True
                except Exception as e:
                    logger.warning("Failed to delete %s: %s", self.auth_file, e)
            return False

    def discover_local_tokens(self) -> Optional[AntigravityCredentials]:
        """Disabled by policy: never scan or import local Antigravity CLI/IDE tokens.

        Only accounts explicitly logged in via the plugin OAuth flow
        (~/.hermes/auth/antigravity_tokens.json) are used.
        """
        return None

    def refresh_access_token(self, creds: AntigravityCredentials) -> AntigravityCredentials:
        """Use refresh_token to mint a fresh access token."""
        if not creds.refresh_token:
            raise RuntimeError("No refresh token available to refresh Antigravity credentials.")

        client_id = self.get_client_id()
        client_secret = self.get_client_secret()

        payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": creds.refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=20.0) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        new_access_token = raw.get("access_token")
        if not new_access_token:
            raise RuntimeError(f"Token refresh failed: {raw}")

        expires_in = float(raw.get("expires_in") or 3600.0)
        creds.access_token = new_access_token
        creds.expires_at = time.time() + expires_in
        if raw.get("refresh_token"):
            creds.refresh_token = raw["refresh_token"]

        self.save_credentials(creds)
        logger.info("Successfully refreshed Antigravity OAuth access token")
        return creds

    def resolve_valid_credentials(self, bearer_token: str = "") -> AntigravityCredentials:
        """Resolve a valid, unexpired Antigravity credential from the plugin OAuth store.

        If bearer_token is provided, matches against stored credentials by access_token,
        email, or token prefix; if matched and expired, refreshes it automatically.
        Strictly respects account pool cooldown and disabled states.
        """
        with self._lock:
            all_creds = self.load_all_stored_credentials()
            creds = None
            pool_accounts_map: Dict[str, Any] = {}
            pool = None
            try:
                try:
                    from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
                except ImportError:
                    from bridge.account_pool import AntigravityAccountPoolManager
                pool = AntigravityAccountPoolManager(storage_path=self.auth_file)
                for p_acc in pool.list_accounts():
                    if p_acc.email:
                        pool_accounts_map[p_acc.email.lower()] = p_acc
            except Exception as e:
                logger.debug("Account pool lookup failed: %s", e)

            if bearer_token and all_creds:
                for c in all_creds:
                    if (
                        c.access_token == bearer_token
                        or (bearer_token.startswith("ya29.") and c.access_token.startswith(bearer_token[:20]))
                        or c.email.lower() == bearer_token.lower()
                        or (c.email and c.email.lower().startswith(bearer_token.lower()))
                    ):
                        p_acc = pool_accounts_map.get((c.email or "").lower())
                        if p_acc is not None and not p_acc.is_available:
                            raise RuntimeError(
                                f"Antigravity account '{c.email}' is currently {p_acc.status} and unavailable."
                            )
                        creds = c
                        break

            if not creds and pool is not None:
                acc = pool.get_next_available_account()
                if acc:
                    creds = AntigravityCredentials(
                        access_token=acc.access_token,
                        refresh_token=acc.refresh_token,
                        expires_at=acc.expires_at,
                        email=acc.email,
                        project_id=acc.project_id,
                        managed_project_id=acc.managed_project_id,
                        tier_id=acc.tier_id,
                        source=acc.source,
                    )
                elif pool_accounts_map:
                    raise RuntimeError(
                        "All Antigravity OAuth accounts in the pool are currently cooling down or disabled."
                    )

            if not creds and not pool_accounts_map:
                creds = self.load_stored_credentials()

            if not creds:
                raise RuntimeError(
                    "No Antigravity OAuth credentials found. Please run 'python scripts/antigravity_bridge.py login' "
                    "or log in via the Antigravity Bridge UI."
                )

            if creds.is_expired:
                if creds.refresh_token:
                    creds = self.refresh_access_token(creds)
                else:
                    raise RuntimeError(
                        f"Antigravity access token for {creds.email or 'account'} is expired and no refresh token is present. Please re-login."
                    )

            if creds.managed_project_id and creds.managed_project_id != DEFAULT_PROJECT_ID:
                if not creds.project_id or creds.project_id == DEFAULT_PROJECT_ID:
                    creds.project_id = creds.managed_project_id

            if not creds.project_id or (creds.project_id == DEFAULT_PROJECT_ID and not creds.managed_project_id):
                em_cache_key = (creds.email or "primary").strip().lower()
                cached_pid = self._resolved_project_cache.get(em_cache_key)
                if cached_pid:
                    creds.project_id = cached_pid
                else:
                    resolved_pid = self.resolve_project_id(creds)
                    if resolved_pid:
                        self._resolved_project_cache[em_cache_key] = resolved_pid
                        if resolved_pid != creds.project_id and resolved_pid != DEFAULT_PROJECT_ID:
                            creds.project_id = resolved_pid
                            self.save_credentials(creds)
                        else:
                            creds.project_id = resolved_pid

            return creds

    @staticmethod
    def _extract_companion_project_id(data: Dict[str, Any]) -> str:
        """Extract cloudaicompanionProject from loadCodeAssist or onboardUser response."""
        if not isinstance(data, dict):
            return ""
        raw_proj = data.get("cloudaicompanionProject")
        if isinstance(raw_proj, str) and raw_proj.strip():
            return raw_proj.strip()
        if isinstance(raw_proj, dict):
            pid = raw_proj.get("id") or raw_proj.get("projectId") or ""
            if isinstance(pid, str) and pid.strip():
                return pid.strip()
        for key in ("projectId", "project_id"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    def resolve_project_id(self, creds: Any) -> str:
        """Resolve Google Cloud Companion Project ID via authentic loadCodeAssist + onboardUser handshake."""
        if isinstance(creds, str):
            creds = AntigravityCredentials(access_token=creds)
        env_proj = (os.getenv(ENV_PROJECT_ID) or "").strip()
        if env_proj:
            return env_proj
        if creds.managed_project_id and creds.managed_project_id != DEFAULT_PROJECT_ID:
            creds.project_id = creds.managed_project_id
            return creds.managed_project_id
        if creds.project_id and creds.project_id != DEFAULT_PROJECT_ID:
            return creds.project_id

        try:
            try:
                from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
            except ImportError:
                from bridge.fingerprint import AntigravityFingerprint
            headers = AntigravityFingerprint.build_headers(creds.access_token)
            metadata = AntigravityFingerprint.build_client_metadata()
        except Exception:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "Authorization": f"Bearer {creds.access_token}",
                "User-Agent": "antigravity/2.23.1 (aidev_client; os_type=windows; arch=amd64; cl=998881661)",
            }
            metadata = {
                "ideType": "ANTIGRAVITY",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
                "ideVersion": "2.23.1",
            }

        try:
            load_body = json.dumps({"metadata": metadata}).encode("utf-8")
            data: Dict[str, Any] = {}
            for endpoint in (LOAD_CODE_ASSIST_ENDPOINT, FALLBACK_LOAD_CODE_ASSIST_ENDPOINT):
                try:
                    req = urllib.request.Request(
                        endpoint,
                        data=load_body,
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        raw_bytes = resp.read()
                        if resp.headers.get("Content-Encoding") == "gzip" or raw_bytes[:2] == b"\x1f\x8b":
                            import gzip
                            raw_bytes = gzip.decompress(raw_bytes)
                        data = json.loads(raw_bytes.decode("utf-8"))
                    break
                except urllib.error.HTTPError as he:
                    if he.code in {404, 500, 502, 503, 504} and endpoint == LOAD_CODE_ASSIST_ENDPOINT:
                        continue
                    raise

            paid_tier = data.get("paidTier")
            current_tier = data.get("currentTier")
            tier_id = ""
            plan_name = ""
            plan_type = "free"
            if isinstance(paid_tier, dict) and paid_tier.get("name"):
                plan_name = str(paid_tier.get("name"))
                tier_id = str(paid_tier.get("id") or "")
            if not plan_name and isinstance(current_tier, dict):
                plan_name = str(current_tier.get("name") or "")
                if not tier_id:
                    tier_id = str(current_tier.get("id") or "")
            if not tier_id:
                tier_id = str(data.get("tierId") or "")

            p_low = plan_name.lower()
            t_low = tier_id.lower()
            if "ultra" in p_low or "ultra" in t_low:
                plan_type = "ultra"
                plan_name = plan_name or "Google AI Ultra"
            elif "pro" in p_low or "pro" in t_low:
                plan_type = "pro"
                plan_name = plan_name or "Google AI Pro"
            else:
                plan_type = "free"
                plan_name = plan_name or "Free Tier"

            if tier_id:
                creds.tier_id = tier_id
            creds.plan_name = plan_name
            creds.plan_type = plan_type

            pid = self._extract_companion_project_id(data)
            if not pid or not current_tier:
                # Account has not completed onboarding yet; invoke onboardUser with default tier
                allowed_tiers = data.get("allowedTiers")
                onboard_tier_id = tier_id or "free-tier"
                if isinstance(allowed_tiers, list) and allowed_tiers:
                    for t in allowed_tiers:
                        if isinstance(t, dict) and t.get("isDefault") and t.get("id"):
                            onboard_tier_id = str(t["id"])
                            break
                    else:
                        first_t = allowed_tiers[0]
                        if isinstance(first_t, dict) and first_t.get("id"):
                            onboard_tier_id = str(first_t["id"])

                onboard_body = json.dumps({
                    "tierId": onboard_tier_id,
                    "metadata": metadata,
                }).encode("utf-8")
                ob_data: Dict[str, Any] = {}
                for ob_endpoint in (ONBOARD_USER_ENDPOINT, FALLBACK_ONBOARD_USER_ENDPOINT):
                    try:
                        onboard_req = urllib.request.Request(
                            ob_endpoint,
                            data=onboard_body,
                            headers=headers,
                            method="POST",
                        )
                        with urllib.request.urlopen(onboard_req, timeout=12.0) as ob_resp:
                            raw_ob = ob_resp.read()
                            if ob_resp.headers.get("Content-Encoding") == "gzip" or raw_ob[:2] == b"\x1f\x8b":
                                import gzip
                                raw_ob = gzip.decompress(raw_ob)
                            ob_data = json.loads(raw_ob.decode("utf-8"))
                        break
                    except urllib.error.HTTPError as he:
                        if he.code in {404, 500, 502, 503, 504} and ob_endpoint == ONBOARD_USER_ENDPOINT:
                            continue
                        raise
                onboard_pid = self._extract_companion_project_id(ob_data)
                if not onboard_pid and isinstance(ob_data.get("response"), dict):
                    onboard_pid = self._extract_companion_project_id(ob_data["response"])
                if onboard_pid:
                    pid = onboard_pid
                if onboard_tier_id and not creds.tier_id:
                    creds.tier_id = onboard_tier_id

            if pid:
                creds.project_id = pid
                creds.managed_project_id = pid
                return pid
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                raw_err = e.read()
                if raw_err[:2] == b"\x1f\x8b":
                    import gzip
                    raw_err = gzip.decompress(raw_err)
                err_body = raw_err.decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code == 403 and ("violation of terms of service" in err_body.lower() or "disabled in this account" in err_body.lower()):
                if getattr(creds, "email", ""):
                    try:
                        try:
                            from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
                        except ImportError:
                            from bridge.account_pool import AntigravityAccountPoolManager
                        pool = AntigravityAccountPoolManager(storage_path=self.auth_file)
                        pool.mark_account_disabled(creds.email, reason="HTTP 403 TOS_VIOLATION on loadCodeAssist")
                    except Exception:
                        pass
            logger.debug("loadCodeAssist/onboardUser HTTP %d: %s", e.code, err_body[:200])
        except Exception as e:
            logger.debug("loadCodeAssist/onboardUser project discovery fell back: %s", e)

        return creds.project_id or DEFAULT_PROJECT_ID

    def probe_account_unlock_status(self, email: str) -> Dict[str, Any]:
        """Probe Google Code Assist (loadCodeAssist + fetchAvailableModels) for a specific account to check if it has been unlocked.

        If Google returns 200 OK on both endpoints, automatically restores the account status to 'active' in the pool.
        If Google still returns 403 TOS_VIOLATION, keeps it 'disabled' and extracts the appeal URL.
        """
        target = (email or "").strip().lower()
        if not target:
            return {"ok": False, "unlocked": False, "message": "Email tài khoản không hợp lệ."}

        try:
            from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
        except ImportError:
            from bridge.account_pool import AntigravityAccountPoolManager

        pool = AntigravityAccountPoolManager(storage_path=self.auth_file)
        acc = pool.get_account(target)
        if not acc:
            return {"ok": False, "unlocked": False, "message": f"Không tìm thấy tài khoản '{target}' trong pool."}

        creds = AntigravityCredentials(
            access_token=acc.access_token,
            refresh_token=acc.refresh_token,
            expires_at=acc.expires_at,
            email=acc.email,
            project_id=acc.project_id,
            managed_project_id=acc.managed_project_id,
            tier_id=acc.tier_id,
            source=acc.source,
        )
        if creds.is_expired and creds.refresh_token:
            try:
                creds = self.refresh_access_token(creds)
            except Exception as e:
                return {
                    "ok": False,
                    "email": target,
                    "unlocked": False,
                    "status": acc.status,
                    "message": f"Không thể làm mới token cho {target} (vui lòng đăng nhập lại): {e}",
                }

        try:
            try:
                from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
            except ImportError:
                from bridge.fingerprint import AntigravityFingerprint
            headers = AntigravityFingerprint.build_headers(creds.access_token)
            metadata = AntigravityFingerprint.build_client_metadata()
        except Exception:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "Authorization": f"Bearer {creds.access_token}",
                "User-Agent": "antigravity/2.23.1 (aidev_client; os_type=windows; arch=amd64; cl=998881661)",
            }
            metadata = {
                "ideType": "ANTIGRAVITY",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
                "ideVersion": "2.23.1",
            }

        try:
            existing_pid = creds.effective_project_id
            candidate_payloads = []
            if existing_pid and existing_pid != DEFAULT_PROJECT_ID:
                candidate_payloads.append({"cloudaicompanionProject": existing_pid, "metadata": metadata})
                candidate_payloads.append({"metadata": metadata})
            else:
                candidate_payloads.append({"metadata": metadata})
                if existing_pid:
                    candidate_payloads.append({"cloudaicompanionProject": existing_pid, "metadata": metadata})

            data: Dict[str, Any] = {}
            last_probe_err: Optional[Exception] = None
            for payload_dict in candidate_payloads:
                load_body = json.dumps(payload_dict).encode("utf-8")
                try:
                    req = urllib.request.Request(
                        LOAD_CODE_ASSIST_ENDPOINT,
                        data=load_body,
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=12.0) as resp:
                        raw_bytes = resp.read()
                        if resp.headers.get("Content-Encoding") == "gzip" or raw_bytes[:2] == b"\x1f\x8b":
                            import gzip
                            raw_bytes = gzip.decompress(raw_bytes)
                        data = json.loads(raw_bytes.decode("utf-8"))
                    if data:
                        break
                except Exception as p_err:
                    last_probe_err = p_err
                    continue
            if not data and last_probe_err is not None:
                raise last_probe_err

            paid_tier = data.get("paidTier")
            current_tier = data.get("currentTier")
            tier_id = ""
            plan_name = ""
            if isinstance(paid_tier, dict) and paid_tier.get("name"):
                plan_name = str(paid_tier.get("name"))
                tier_id = str(paid_tier.get("id") or "")
            if not plan_name and isinstance(current_tier, dict):
                plan_name = str(current_tier.get("name") or "")
                if not tier_id:
                    tier_id = str(current_tier.get("id") or "")
            if not tier_id:
                tier_id = str(data.get("tierId") or "")
            pid = self._extract_companion_project_id(data) or creds.effective_project_id or DEFAULT_PROJECT_ID

            # Step 2: Verify model catalog access via fetchAvailableModels because loadCodeAssist
            # can return HTTP 200 OK even when the account is blocked with 403 TOS_VIOLATION.
            models_endpoints = (
                "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
                "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
            )
            models_body = json.dumps({"project": pid}).encode("utf-8")
            models_headers = dict(headers)
            if pid:
                models_headers["X-Goog-User-Project"] = pid
            for m_ep in models_endpoints:
                try:
                    m_req = urllib.request.Request(
                        m_ep,
                        data=models_body,
                        headers=models_headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(m_req, timeout=12.0) as m_resp:
                        _ = m_resp.read()
                    break
                except urllib.error.HTTPError as m_he:
                    if m_he.code in {404, 500, 502, 503, 504} and m_ep == models_endpoints[0]:
                        continue
                    raise

            p_low = plan_name.lower()
            t_low = tier_id.lower()
            if "ultra" in p_low or "ultra" in t_low:
                creds.plan_type = "ultra"
                plan_name = plan_name or "Google AI Ultra"
            elif "pro" in p_low or "pro" in t_low:
                creds.plan_type = "pro"
                plan_name = plan_name or "Google AI Pro"
            else:
                creds.plan_type = "free"
                plan_name = "Free Tier" if ("free" in t_low or "antigravity" in p_low) else (plan_name or "Free Tier")

            creds.project_id = pid
            creds.managed_project_id = pid
            if tier_id:
                creds.tier_id = tier_id
            if plan_name:
                creds.plan_name = plan_name

            self.save_credentials(creds, reset_status=True)
            pool.add_or_update_account(creds, reset_status=True)
            return {
                "ok": True,
                "email": target,
                "unlocked": True,
                "status": "active",
                "project_id": pid,
                "tier_id": tier_id or "free-tier",
                "message": f"Tài khoản {target} ĐÃ ĐƯỢC GOOGLE MỞ KHÓA và khôi phục trạng thái SẴN SÀNG!",
            }
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                raw_err = e.read()
                if raw_err[:2] == b"\x1f\x8b":
                    import gzip
                    raw_err = gzip.decompress(raw_err)
                err_body = raw_err.decode("utf-8", errors="replace")
            except Exception:
                pass
            appeal_url = "https://forms.gle/hGzM9MEUv2azZsrb9"
            reason = f"HTTP_{e.code}"
            try:
                err_json = json.loads(err_body)
                details = err_json.get("error", {}).get("details", [])
                for d in details:
                    if isinstance(d, dict):
                        if d.get("reason"):
                            reason = str(d["reason"])
                        meta_d = d.get("metadata")
                        if isinstance(meta_d, dict) and meta_d.get("appeal_url"):
                            appeal_url = str(meta_d["appeal_url"])
            except Exception:
                pass

            if e.code == 403 and (
                "tos_violation" in reason.lower()
                or "permission_denied" in reason.lower()
                or "violation of terms of service" in err_body.lower()
                or "disabled in this account" in err_body.lower()
                or "permission_denied" in err_body.lower()
            ):
                pool.mark_account_disabled(target, reason=f"HTTP 403 {reason}")
                return {
                    "ok": True,
                    "email": target,
                    "unlocked": False,
                    "status": "disabled",
                    "reason": reason,
                    "appeal_url": appeal_url,
                    "message": f"Tài khoản {target} vẫn đang bị Google khóa ({reason}). Link kháng nghị: {appeal_url}",
                }
            return {
                "ok": False,
                "email": target,
                "unlocked": False,
                "status": acc.status,
                "reason": reason,
                "message": f"Kiểm tra {target} trả về HTTP {e.code}: {err_body[:160]}",
            }
        except Exception as e:
            return {
                "ok": False,
                "email": target,
                "unlocked": False,
                "status": acc.status,
                "message": f"Lỗi kết nối khi kiểm tra {target}: {e}",
            }

    def create_pkce_auth_session(self, port: int = DEFAULT_REDIRECT_PORT) -> Dict[str, Any]:
        """Generate a PKCE authorization session (URL + verifier + state) for remote/mobile or local login."""
        session_id = secrets.token_hex(16)
        code_verifier = secrets.token_urlsafe(64)[:128]
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        state = secrets.token_hex(16)
        redirect_uri = f"http://{REDIRECT_HOST}:{port}{CALLBACK_PATH}"
        client_id = self.get_client_id()

        auth_params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": OAUTH_SCOPES,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(auth_params)}"
        return {
            "session_id": session_id,
            "code_verifier": code_verifier,
            "state": state,
            "redirect_uri": redirect_uri,
            "port": port,
            "auth_url": auth_url,
            "created_at": time.time(),
            "expires_at": time.time() + 600.0,
        }

    def complete_pkce_auth_session(
        self,
        callback_or_code: str,
        code_verifier: str,
        redirect_uri: str,
        expected_state: Optional[str] = None,
    ) -> AntigravityCredentials:
        """Exchange a pasted callback URL (or raw authorization code) for OAuth tokens and onboard account."""
        raw = (callback_or_code or "").strip()
        if not raw:
            raise ValueError("Vui lòng nhập đường link callback hoặc mã code OAuth.")

        auth_code = raw
        if "://" in raw or raw.startswith("localhost:") or raw.startswith("127.0.0.1:") or "?" in raw or "code=" in raw:
            if not raw.startswith("http") and ("localhost" in raw or "127.0.0.1" in raw):
                raw = "http://" + raw
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            if not qs and "code=" in raw:
                qs = urllib.parse.parse_qs(raw.split("?", 1)[-1])
            if "error" in qs and qs["error"]:
                raise RuntimeError(f"Google OAuth trả về lỗi: {qs['error'][0]}")
            returned_state = qs.get("state", [None])[0]
            if expected_state and returned_state != expected_state:
                raise ValueError("State OAuth không khớp hoặc bị thiếu (vui lòng dùng đúng link đăng nhập vừa mở).")
            extracted_code = qs.get("code", [None])[0]
            if not extracted_code:
                raise ValueError("Không tìm thấy tham số 'code=' trong đường link đã dán.")
            auth_code = extracted_code

        client_id = self.get_client_id()
        client_secret = self.get_client_secret()
        token_payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }).encode("utf-8")

        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))

        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError("Không nhận được access_token từ Google OAuth.")
        refresh_token = token_data.get("refresh_token") or ""
        expires_in = float(token_data.get("expires_in") or 3600.0)

        email = ""
        try:
            user_req = urllib.request.Request(
                f"{USERINFO_ENDPOINT}?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urllib.request.urlopen(user_req, timeout=10.0) as user_resp:
                user_info = json.loads(user_resp.read().decode("utf-8"))
                email = user_info.get("email") or ""
        except Exception:
            pass

        creds = AntigravityCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
            email=email,
            source="oauth_pkce",
        )
        creds.project_id = self.resolve_project_id(creds)
        self.save_credentials(creds)
        return creds

    def login_interactive(
        self,
        port: int = DEFAULT_REDIRECT_PORT,
        open_browser: bool = True,
        timeout_seconds: float = 300.0,
    ) -> AntigravityCredentials:
        """Alias for login_pkce."""
        return self.login_pkce(port=port, open_browser=open_browser, timeout_seconds=timeout_seconds)

    def login_pkce(
        self,
        port: int = DEFAULT_REDIRECT_PORT,
        open_browser: bool = True,
        timeout_seconds: float = 300.0,
    ) -> AntigravityCredentials:
        """Execute Google OAuth 2.0 Authorization Code flow with PKCE."""
        session = self.create_pkce_auth_session(port=port)
        code_verifier = session["code_verifier"]
        state = session["state"]
        redirect_uri = session["redirect_uri"]
        auth_url = session["auth_url"]
        client_id = self.get_client_id()
        client_secret = self.get_client_secret()

        auth_code_holder: Dict[str, Optional[str]] = {"code": None, "error": None}

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == CALLBACK_PATH:
                    qs = urllib.parse.parse_qs(parsed.query)
                    returned_state = qs.get("state", [None])[0]
                    if returned_state != state:
                        auth_code_holder["error"] = "State mismatch in OAuth callback"
                        self._send_html("<h3>Authentication Error</h3><p>State verification failed.</p>", 400)
                        return
                    code = qs.get("code", [None])[0]
                    if code:
                        auth_code_holder["code"] = code
                        self._send_html(
                            "<html><body style='font-family:sans-serif;text-align:center;padding-top:40px;'>"
                            "<h2 style='color:#10b981;'>Antigravity OAuth Successful!</h2>"
                            "<p>You can now close this tab and return to Hermes.</p>"
                            "</body></html>",
                            200,
                        )
                    else:
                        auth_code_holder["error"] = qs.get("error", ["Unknown error"])[0]
                        safe_err = html.escape(str(auth_code_holder["error"]))
                        self._send_html(f"<h3>Authentication Failed</h3><p>{safe_err}</p>", 400)
                else:
                    self.send_response(404)
                    self.end_headers()

            def _send_html(self, html: str, status: int):
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

            def log_message(self, format, *args):
                pass  # Suppress request logging

        server = HTTPServer((REDIRECT_HOST, port), OAuthCallbackHandler)
        server.timeout = 1.0

        if open_browser:
            logger.info("Opening browser for Antigravity OAuth: %s", auth_url)
            webbrowser.open(auth_url)
        else:
            print(f"\nPlease open this URL in your browser to log in with Google Antigravity:\n{auth_url}\n")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            server.handle_request()
            if auth_code_holder["code"] or auth_code_holder["error"]:
                break

        server.server_close()

        if auth_code_holder["error"]:
            raise RuntimeError(f"OAuth error: {auth_code_holder['error']}")
        if not auth_code_holder["code"]:
            raise TimeoutError("Timed out waiting for Google OAuth callback.")

        auth_code = auth_code_holder["code"]

        token_payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }).encode("utf-8")

        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=20.0) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token") or ""
        expires_in = float(token_data.get("expires_in") or 3600.0)

        # Get user email
        email = ""
        try:
            user_req = urllib.request.Request(
                f"{USERINFO_ENDPOINT}?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urllib.request.urlopen(user_req, timeout=10.0) as user_resp:
                user_info = json.loads(user_resp.read().decode("utf-8"))
                email = user_info.get("email") or ""
        except Exception:
            pass

        creds = AntigravityCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
            email=email,
            source="oauth_pkce",
        )
        creds.project_id = self.resolve_project_id(creds)
        self.save_credentials(creds)
        logger.info("Successfully authenticated Antigravity OAuth for %s", email or "user")
        return creds
