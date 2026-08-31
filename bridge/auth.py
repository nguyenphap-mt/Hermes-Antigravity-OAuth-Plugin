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
            source=data.get("source") or "stored",
        )


class AntigravityAuthManager:
    """Manages token resolution, storage, and PKCE login for Antigravity."""

    def __init__(self, auth_file: Optional[Path] = None) -> None:
        self._auth_file_is_custom = auth_file is not None
        self.auth_file = auth_file or (get_hermes_dir() / "auth" / "antigravity_tokens.json")
        self._lock = threading.Lock()

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
        """Load all stored credentials (multi-account) from auth file and standard locations."""
        if self._auth_file_is_custom:
            candidate_files = [self.auth_file]
        else:
            candidate_files = [
                self.auth_file,
                get_hermes_dir() / "auth" / "antigravity_tokens.json",
                Path.home() / ".hermes" / "auth" / "antigravity_tokens.json",
            ]
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
                                em = acct_data.get("email") or email_key
                                if em not in seen_emails:
                                    seen_emails.add(em)
                                    creds_list.append(AntigravityCredentials.from_dict(acct_data))
                    if data.get("access_token"):
                        em = data.get("email") or "primary"
                        if em not in seen_emails:
                            seen_emails.add(em)
                            creds_list.append(AntigravityCredentials.from_dict(data))
            except Exception as e:
                logger.warning("Failed to read credentials from %s: %s", cpath, e)

        return creds_list

    def load_stored_credentials(self, email: Optional[str] = None) -> Optional[AntigravityCredentials]:
        """Load credentials from ~/.hermes/auth/antigravity_tokens.json."""
        all_creds = self.load_all_stored_credentials()
        if not all_creds:
            return None
        if email:
            for c in all_creds:
                if c.email.lower() == email.lower():
                    return c
        return all_creds[0]

    def save_credentials(self, creds: AntigravityCredentials) -> None:
        """Save credentials atomically preserving all accounts and syncing to all profile auth stores."""
        if self._auth_file_is_custom:
            target_token_files = [self.auth_file]
        else:
            target_token_files = [
                self.auth_file,
                get_hermes_dir() / "auth" / "antigravity_tokens.json",
                Path.home() / ".hermes" / "auth" / "antigravity_tokens.json",
            ]
        try:
            existing_data: Dict[str, Any] = {}
            for tf in target_token_files:
                if tf.is_file():
                    with contextlib.suppress(Exception):
                        with open(tf, "r", encoding="utf-8") as f:
                            existing_data = json.load(f)
                            if existing_data.get("accounts"):
                                break

            accounts = existing_data.get("accounts")
            if not isinstance(accounts, dict):
                accounts = {}
                if existing_data.get("access_token"):
                    prev_email = existing_data.get("email") or "primary"
                    accounts[prev_email] = existing_data

            email_key = creds.email or "primary"
            accounts[email_key] = creds.to_dict()

            out_data = creds.to_dict()
            out_data["accounts"] = accounts

            # Save token files
            for tf in target_token_files:
                try:
                    tf.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = tf.with_suffix(".tmp")
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        json.dump(out_data, f, indent=2)
                    if os.name != "nt":
                        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
                    shutil.move(str(tmp_path), str(tf))
                except Exception as e:
                    logger.debug("Failed saving token file to %s: %s", tf, e)

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
                "project_id": creds.project_id,
                "expires_at": creds.expires_at,
                "updated_at": time.time(),
            }

            # Sync to all auth.json stores (root + profiles)
            auth_store_targets = [
                get_hermes_dir() / "auth.json",
                Path.home() / ".hermes" / "auth.json",
            ]
            profiles_dir = get_hermes_dir() / "profiles"
            if profiles_dir.is_dir():
                for pdir in profiles_dir.iterdir():
                    if pdir.is_dir():
                        auth_store_targets.append(pdir / "auth.json")

            for ast in auth_store_targets:
                try:
                    ast.parent.mkdir(parents=True, exist_ok=True)
                    store: Dict[str, Any] = {}
                    if ast.is_file():
                        with contextlib.suppress(Exception):
                            with open(ast, "r", encoding="utf-8") as af:
                                store = json.load(af)

                    store.setdefault("credential_pool", {})["antigravity"] = pool_entries
                    store.setdefault("providers", {})["antigravity"] = provider_payload

                    tmp_ast = ast.with_suffix(".tmp")
                    with open(tmp_ast, "w", encoding="utf-8") as af:
                        json.dump(store, af, indent=2)
                    shutil.move(str(tmp_ast), str(ast))
                except Exception as e:
                    logger.debug("Failed syncing auth store to %s: %s", ast, e)

        except Exception as e:
            logger.error("Failed to save credentials: %s", e)
            if tmp_path.exists():
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
        """Scan local Antigravity CLI/IDE session files for existing tokens."""
        candidate_paths = [
            Path.home() / ".gemini" / "antigravity-cli" / "settings.json",
            Path.home() / ".gemini" / "antigravity" / "settings.json",
            Path.home() / ".gemini" / "settings.json",
        ]
        for path in candidate_paths:
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                access_token = data.get("access_token") or data.get("oauth_token") or data.get("token")
                refresh_token = data.get("refresh_token") or ""
                expires_at = float(data.get("expires_at") or 0.0)
                email = data.get("email") or ""
                project_id = data.get("project_id") or ""
                if access_token:
                    logger.info("Discovered local Antigravity token from %s", path)
                    return AntigravityCredentials(
                        access_token=access_token,
                        refresh_token=refresh_token,
                        expires_at=expires_at,
                        email=email,
                        project_id=project_id,
                        source=f"discovered:{path.name}",
                    )
            except Exception:
                continue
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
        """Resolve a valid, unexpired Antigravity credential (stored or discovered).
        
        If bearer_token is provided, matches against stored credentials by access_token,
        email, or token prefix; if matched and expired, refreshes it automatically.
        """
        with self._lock:
            all_creds = self.load_all_stored_credentials()
            creds = None
            if bearer_token and all_creds:
                            for c in all_creds:
                                # Exact match on the full access token.
                                if c.access_token == bearer_token:
                                    creds = c
                                    break
                                # Google OAuth access tokens all start with "ya29."; use a
                                # 40-char prefix match (long enough to avoid collisions
                                # between distinct accounts) instead of only 20 chars.
                                if (
                                    bearer_token.startswith("ya29.")
                                    and c.access_token.startswith(bearer_token[:40])
                                ):
                                    creds = c
                                    break
                                # Match by full email only — prefix matching would let
                                # "user" match "user@example.com" AND "user@other.com".
                                if c.email == bearer_token:
                                    creds = c
                                    break

            if not creds:
                creds = self.load_stored_credentials()
            if not creds:
                creds = self.discover_local_tokens()
                if creds:
                    self.save_credentials(creds)

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

            if not creds.project_id:
                creds.project_id = self.resolve_project_id(creds)
                self.save_credentials(creds)

            return creds

    def resolve_project_id(self, creds: AntigravityCredentials) -> str:
        """Resolve Google Cloud Project ID from environment, stored creds, or Code Assist."""
        env_proj = (os.getenv(ENV_PROJECT_ID) or "").strip()
        if env_proj:
            return env_proj
        if creds.project_id:
            return creds.project_id

        # Try loadCodeAssist
        try:
            req = urllib.request.Request(
                LOAD_CODE_ASSIST_ENDPOINT,
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {creds.access_token}",
                    "User-Agent": "Antigravity/1.0.0 windows/amd64",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pid = data.get("cloudaicompanionProject") or data.get("projectId") or data.get("project_id") or ""
            if pid:
                creds.project_id = pid
                creds.managed_project_id = pid
                creds.tier_id = data.get("tierId") or ""
                return pid
        except Exception as e:
            logger.debug("loadCodeAssist project discovery fell back to default: %s", e)

        return DEFAULT_PROJECT_ID

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
        code_verifier = secrets.token_urlsafe(64)[:128]
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        state = secrets.token_hex(16)
        redirect_uri = f"http://{REDIRECT_HOST}:{port}{CALLBACK_PATH}"
        client_id = self.get_client_id()
        client_secret = self.get_client_secret()

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
                        self._send_html(f"<h3>Authentication Failed</h3><p>{auth_code_holder['error']}</p>", 400)
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
