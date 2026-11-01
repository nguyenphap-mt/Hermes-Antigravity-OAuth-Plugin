"""Session, Cookie Parser, Handshake & 9-Minute RotateCookies Manager for Gemini Web App.

Security Architecture:
- Secret cookie values (`__Secure-1PSID`, `__Secure-1PSIDTS`, `SNlM0e`, etc.) are stored exclusively
  in `~/.hermes/gemini_web_sessions.json` with `0o600` permissions.
- Public node metadata in `gemini_web_pool.json` only stores masked previews and health flags.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .models import _default_node_models_list, scrape_models_and_tier_from_html

logger = logging.getLogger(__name__)

GEMINI_WEB_APP_URL = "https://gemini.google.com/app?hl=vi"
ROTATE_COOKIES_URL = "https://accounts.google.com/RotateCookies"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

ROTATE_INTERVAL_SECONDS = 540.0  # 9 minutes


def get_hermes_dir() -> Path:
    """Resolve active Hermes home directory."""
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def _mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 10:
        return val[:2] + "***"
    return f"{val[:6]}...{val[-4:]}"


def parse_flexible_cookie_input(
    raw_input: str = "",
    psid: str = "",
    psidts: str = "",
) -> Dict[str, str]:
    """Parse Google cookies (`__Secure-1PSID`, `__Secure-1PSIDTS`, etc.) from any user input format:
    1. Explicit `psid` and `psidts` arguments
    2. JSON array exported from Cookie-Editor / EditThisCookie
    3. JSON key-value object `{"__Secure-1PSID": "...", "__Secure-1PSIDTS": "..."}`
    4. Full `curl` command containing `-H 'cookie: ...'` or `-b '...'`
    5. Raw HTTP `Cookie: name=val; name2=val2` string
    """
    cookies: Dict[str, str] = {}

    if psid and psid.strip():
        cookies["__Secure-1PSID"] = psid.strip()
    if psidts and psidts.strip():
        cookies["__Secure-1PSIDTS"] = psidts.strip()

    text = (raw_input or "").strip()
    if not text:
        return cookies

    # 1. Try JSON parsing (Cookie-Editor array, Playwright storage-state.json, or dict)
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
        try:
            parsed = json.loads(text)
            cookie_list: Optional[List[ Any]] = None
            if isinstance(parsed, list):
                cookie_list = parsed
            elif isinstance(parsed, dict) and isinstance(parsed.get("cookies"), list):
                cookie_list = parsed["cookies"]

            if cookie_list is not None:
                fallback_cookies: Dict[str, str] = {}
                for item in cookie_list:
                    if not isinstance(item, dict) or not item.get("name") or item.get("value") is None:
                        continue
                    c_name = str(item["name"]).strip()
                    c_val = str(item["value"]).strip()
                    c_domain = str(item.get("domain") or "").strip().lower()
                    if not c_domain or c_domain in (
                        ".google.com",
                        "google.com",
                        "gemini.google.com",
                        ".gemini.google.com",
                        "accounts.google.com",
                    ):
                        cookies[c_name] = c_val
                    elif c_name not in fallback_cookies:
                        fallback_cookies[c_name] = c_val
                for k, v in fallback_cookies.items():
                    if k not in cookies:
                        cookies[k] = v
                if "__Secure-1PSID" in cookies:
                    return cookies
            elif isinstance(parsed, dict):
                for k, v in parsed.items():
                    if v is not None and not isinstance(v, (list, dict)):
                        cookies[str(k).strip()] = str(v).strip()
                if "__Secure-1PSID" in cookies:
                    return cookies
        except Exception:
            pass

    # 2. Extract from cURL command if present
    if "curl " in text.lower() or "-h " in text.lower() or "--cookie" in text.lower():
        header_matches = re.findall(
            r"(?:-H|--header|-b|--cookie)\s+['\"](?:cookie:\s*)?([^'\"]+)['\"]",
            text,
            flags=re.IGNORECASE,
        )
        for hm in header_matches:
            if "__Secure-1PSID" in hm or "SID=" in hm:
                text = hm
                break

    # 3. Strip leading "Cookie:" prefix if present
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()

    # 4. Parse semicolon- or newline-delimited key=value pairs
    for chunk in re.split(r"[;\n\r]+", text):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k = k.strip().strip("'\"")
        v = v.strip().strip("'\"")
        if k:
            cookies[k] = v

    return cookies


class GeminiWebSessionManager:
    """Manages encrypted/0600 cookie sessions, CSRF tokens (`SNlM0e`), and 9-minute `RotateCookies`."""

    def __init__(self, hermes_dir: Optional[Path] = None) -> None:
        self.hermes_dir = hermes_dir or get_hermes_dir()
        self.sessions_file = self.hermes_dir / "gemini_web_sessions.json"

    def _load_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        if not self.sessions_file.is_file():
            return {}
        try:
            with open(self.sessions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("sessions", {}) if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Failed to read gemini_web_sessions.json: %s", e)
            return {}

    def _save_all_sessions(self, sessions: Dict[str, Dict[str, Any]]) -> None:
        self.hermes_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": time.time(),
            "sessions": sessions,
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.hermes_dir),
            prefix=".gweb_sessions_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            try:
                os.chmod(tmp_path, 0o600)
            except Exception:
                pass
            os.replace(tmp_path, str(self.sessions_file))
            try:
                os.chmod(str(self.sessions_file), 0o600)
            except Exception:
                pass
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            raise

    def get_session(self, node_id: str) -> Optional[Dict[str, Any]]:
        sessions = self._load_all_sessions()
        return sessions.get(node_id)

    def save_session(
        self,
        node_id: str,
        cookies: Dict[str, str],
        snlm0e: str = "",
        cfb2h: str = "",
        fsid: str = "",
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> Dict[str, Any]:
        sessions = self._load_all_sessions()
        existing = sessions.get(node_id, {})
        merged_cookies = dict(existing.get("cookies") or {})
        merged_cookies.update({k: v for k, v in cookies.items() if v})

        now = time.time()
        record = {
            "node_id": node_id,
            "cookies": merged_cookies,
            "snlm0e": snlm0e or existing.get("snlm0e") or "",
            "cfb2h": cfb2h or existing.get("cfb2h") or "",
            "fsid": fsid or existing.get("fsid") or "",
            "user_agent": user_agent or existing.get("user_agent") or DEFAULT_USER_AGENT,
            "last_rotated_at": float(existing.get("last_rotated_at") or now),
            "next_rotation_at": float(now + ROTATE_INTERVAL_SECONDS),
            "consecutive_rotate_failures": int(existing.get("consecutive_rotate_failures") or 0),
            "updated_at": now,
        }
        sessions[node_id] = record
        self._save_all_sessions(sessions)
        return record

    def delete_session(self, node_id: str) -> bool:
        sessions = self._load_all_sessions()
        if node_id in sessions:
            del sessions[node_id]
            self._save_all_sessions(sessions)
            return True
        return False

    def get_public_cookie_health(self, node_id: str) -> Dict[str, Any]:
        """Return safe, masked cookie health metadata for Dashboard display (never exposes raw cookies)."""
        sess = self.get_session(node_id) or {}
        cookies = sess.get("cookies") or {}
        psid = str(cookies.get("__Secure-1PSID") or "")
        psidts = str(cookies.get("__Secure-1PSIDTS") or "")
        snlm0e = str(sess.get("snlm0e") or "")
        now = time.time()
        last_rot = float(sess.get("last_rotated_at") or 0.0)
        next_rot = float(sess.get("next_rotation_at") or 0.0)
        return {
            "has_1psid": bool(psid),
            "has_1psidts": bool(psidts),
            "has_snlm0e": bool(snlm0e),
            "psid_preview": _mask_secret(psid),
            "psidts_preview": _mask_secret(psidts),
            "snlm0e_preview": _mask_secret(snlm0e),
            "last_rotated_at": last_rot,
            "next_rotation_at": next_rot,
            "seconds_until_next_rotation": max(0, int(next_rot - now)) if next_rot > 0 else 0,
            "consecutive_rotate_failures": int(sess.get("consecutive_rotate_failures") or 0),
        }

    async def rotate_1psidts(
        self,
        node_id: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> Tuple[bool, str]:
        """Call POST https://accounts.google.com/RotateCookies to refresh __Secure-1PSIDTS."""
        sess = self.get_session(node_id)
        if not sess:
            return False, f"Session '{node_id}' not found."
        cookies = dict(sess.get("cookies") or {})
        psid = cookies.get("__Secure-1PSID")
        if not psid:
            return False, "Missing __Secure-1PSID cookie."

        headers = {
            "Content-Type": "application/json",
            "User-Agent": sess.get("user_agent") or DEFAULT_USER_AGENT,
            "Origin": "https://gemini.google.com",
            "Referer": "https://gemini.google.com/",
        }
        payload = [655, "-0000000000000000000"]

        close_client = False
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
            close_client = True

        try:
            resp = await http_client.post(
                ROTATE_COOKIES_URL,
                content=json.dumps(payload),
                headers=headers,
                cookies=cookies,
            )
            now = time.time()
            sessions = self._load_all_sessions()
            cur = sessions.get(node_id, sess)
            cur_cookies = dict(cur.get("cookies") or {})

            new_psidts = resp.cookies.get("__Secure-1PSIDTS")
            if not new_psidts:
                for k, v in resp.headers.multi_items():
                    if k.lower() == "set-cookie" and "__Secure-1PSIDTS=" in v:
                        m = re.search(r"__Secure-1PSIDTS=([^;]+)", v)
                        if m:
                            new_psidts = m.group(1).strip()
                            break

            if resp.status_code == 200:
                if new_psidts:
                    cur_cookies["__Secure-1PSIDTS"] = new_psidts
                for ck_name, ck_val in resp.cookies.items():
                    if ck_val:
                        cur_cookies[ck_name] = ck_val
                cur["cookies"] = cur_cookies
                cur["last_rotated_at"] = now
                cur["next_rotation_at"] = now + ROTATE_INTERVAL_SECONDS
                cur["consecutive_rotate_failures"] = 0
                cur["updated_at"] = now
                sessions[node_id] = cur
                self._save_all_sessions(sessions)
                return True, "Rotated __Secure-1PSIDTS successfully."

            cur["consecutive_rotate_failures"] = int(cur.get("consecutive_rotate_failures") or 0) + 1
            cur["updated_at"] = now
            sessions[node_id] = cur
            self._save_all_sessions(sessions)
            return False, f"RotateCookies returned HTTP {resp.status_code}"
        except Exception as e:
            logger.warning("Failed to rotate __Secure-1PSIDTS for %s: %s", node_id, e)
            return False, str(e)
        finally:
            if close_client:
                await http_client.aclose()

    async def ensure_fresh_cookie(
        self,
        node_id: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[Dict[str, Any]]:
        """Auto-rotate __Secure-1PSIDTS if more than 9 minutes have elapsed since last rotation."""
        sess = self.get_session(node_id)
        if not sess:
            return None
        now = time.time()
        last_rot = float(sess.get("last_rotated_at") or 0.0)
        if now - last_rot >= ROTATE_INTERVAL_SECONDS:
            await self.rotate_1psidts(node_id, http_client=http_client)
            sess = self.get_session(node_id)
        return sess

    def _resolve_linked_google_account(
        self,
        node_id: str,
        email_hint: str = "",
    ) -> Optional[Dict[str, str]]:
        """Check if `node_id` or `email_hint` matches an authenticated account in `antigravity_tokens.json` or `flow_token.json`."""
        target_email = (email_hint or "").strip().lower()
        cleaned_node = re.sub(r"^gweb_", "", (node_id or "").strip().lower())

        # 1. Check auth/antigravity_tokens.json and antigravity_tokens.json
        for rel in ("auth/antigravity_tokens.json", "antigravity_tokens.json"):
            tf = self.hermes_dir / rel
            if not tf.is_file():
                continue
            try:
                data = json.loads(tf.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                raw_accs = data.get("accounts")
                accounts = list(raw_accs.values()) if isinstance(raw_accs, dict) else (raw_accs if isinstance(raw_accs, list) else [])
                for acc in accounts:
                    if not isinstance(acc, dict):
                        continue
                    em = str(acc.get("email") or "").strip().lower()
                    if not em:
                        continue
                    em_slug = re.sub(r"[^a-zA-Z0-9]+", "_", em).strip("_")[:48]
                    if (
                        (target_email and em == target_email)
                        or (cleaned_node and (em_slug == cleaned_node or em == cleaned_node))
                    ):
                        tier_raw = f"{acc.get('tier_id') or ''} {acc.get('plan_name') or ''} {acc.get('plan_type') or ''}".lower()
                        tier = "ultra" if "ultra" in tier_raw else ("pro" if "pro" in tier_raw else "free")
                        return {
                            "email": em,
                            "display_name": str(acc.get("name") or em.split("@")[0]),
                            "tier": tier,
                            "source": "antigravity_oauth",
                        }
            except Exception:
                pass

        # 2. Check auth/flow_token.json and flow_token.json
        for rel in ("auth/flow_token.json", "flow_token.json"):
            ff = self.hermes_dir / rel
            if not ff.is_file():
                continue
            try:
                fdata = json.loads(ff.read_text(encoding="utf-8"))
                if not isinstance(fdata, dict):
                    continue
                user_obj = fdata.get("user") if isinstance(fdata.get("user"), dict) else {}
                em = str(user_obj.get("email") or fdata.get("email") or "").strip().lower()
                if not em:
                    continue
                em_slug = re.sub(r"[^a-zA-Z0-9]+", "_", em).strip("_")[:48]
                if (
                    not target_email
                    or em == target_email
                    or em_slug == cleaned_node
                ):
                    return {
                        "email": em,
                        "display_name": str(user_obj.get("name") or em.split("@")[0]),
                        "tier": "pro",
                        "source": "flow_token",
                    }
            except Exception:
                pass

        return None

    @staticmethod
    def _is_valid_gemini_app_response(resp: Any, html: str) -> bool:
        """Return False if Google redirected the request to support.google.com or accounts.google.com."""
        final_url = str(getattr(resp, "url", "") or "").lower()
        if final_url and (
            "support.google.com" in final_url
            or "accounts.google.com" in final_url
            or "/faq" in final_url
        ):
            return False
        if "support.google.com/accounts/answer" in html[:4000]:
            return False
        return True

    async def handshake_and_probe_models(
        self,
        node_id: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """Fetch https://gemini.google.com/app to extract SNlM0e, cfb2h, f.sid, email, tier, and models."""
        sess = self.get_session(node_id)
        if not sess:
            return {"ok": False, "error": f"Session '{node_id}' not found."}

        cookies = dict(sess.get("cookies") or {})
        psid_val = str(cookies.get("__Secure-1PSID") or "")
        if not psid_val:
            return {"ok": False, "error": "Missing __Secure-1PSID cookie."}

        # Fast-path for OAuth-linked bridge sessions when raw web cookies are synthetic
        if psid_val.startswith("oauth_linked_"):
            email_hint = psid_val.replace("oauth_linked_", "", 1)
            linked = self._resolve_linked_google_account(node_id, email_hint=email_hint)
            resolved_email = (linked["email"] if linked else email_hint).strip().lower()
            resolved_tier = linked["tier"] if linked else "pro"
            bridge_token = f"oauth_bridge:{resolved_email}"
            self.save_session(
                node_id=node_id,
                cookies=cookies,
                snlm0e=bridge_token,
                cfb2h="boq_assistant-bard-web-server_20260501.08_p0",
                fsid="oauth_bridge_fsid",
            )
            return {
                "ok": True,
                "status": "ready",
                "snlm0e": bridge_token,
                "cfb2h": "boq_assistant-bard-web-server_20260501.08_p0",
                "fsid": "oauth_bridge_fsid",
                "email": resolved_email,
                "detected_tier": resolved_tier,
                "available_models": _default_node_models_list(),
            }

        headers = {
            "User-Agent": sess.get("user_agent") or DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        close_client = False
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=25.0, follow_redirects=True)
            close_client = True

        try:
            resp = await http_client.get(GEMINI_WEB_APP_URL, headers=headers, cookies=cookies)
            html = resp.text or ""

            # Capture any updated cookies from the GET handshake
            for ck_name, ck_val in resp.cookies.items():
                if ck_val:
                    cookies[ck_name] = ck_val

            if self._is_valid_gemini_app_response(resp, html):
                snlm0e_match = re.search(r'"SNlM0e"\s*:\s*"([^"]+)"', html)
                cfb2h_match = re.search(r'"cfb2h"\s*:\s*"([^"]+)"', html)
                fsid_match = re.search(r'"FdrFJe"\s*:\s*"([^"]+)"', html)
                snlm0e = snlm0e_match.group(1) if snlm0e_match else ""
                cfb2h = cfb2h_match.group(1) if cfb2h_match else "boq_assistant-bard-web-server_20260501.08_p0"
                fsid = fsid_match.group(1) if fsid_match else ""
            else:
                snlm0e = ""
                cfb2h = "boq_assistant-bard-web-server_20260501.08_p0"
                fsid = ""

            if not snlm0e:
                # Try rotating cookie once in case __Secure-1PSIDTS was slightly stale
                rot_ok, _ = await self.rotate_1psidts(node_id, http_client=http_client)
                if rot_ok:
                    refreshed_sess = self.get_session(node_id) or {}
                    cookies = dict(refreshed_sess.get("cookies") or {})
                    resp2 = await http_client.get(GEMINI_WEB_APP_URL, headers=headers, cookies=cookies)
                    html = resp2.text or ""
                    if self._is_valid_gemini_app_response(resp2, html):
                        snlm0e_match = re.search(r'"SNlM0e"\s*:\s*"([^"]+)"', html)
                        cfb2h_match = re.search(r'"cfb2h"\s*:\s*"([^"]+)"', html)
                        fsid_match = re.search(r'"FdrFJe"\s*:\s*"([^"]+)"', html)
                        snlm0e = snlm0e_match.group(1) if snlm0e_match else ""
                        cfb2h = cfb2h_match.group(1) if cfb2h_match else cfb2h
                        fsid = fsid_match.group(1) if fsid_match else fsid

            if not snlm0e:
                # Fallback: Check if this browser cookie node belongs to an authenticated Google account in hermes_dir
                linked = self._resolve_linked_google_account(node_id)
                if linked:
                    bridge_token = f"oauth_bridge:{linked['email']}"
                    self.save_session(
                        node_id=node_id,
                        cookies=cookies,
                        snlm0e=bridge_token,
                        cfb2h=cfb2h,
                        fsid=fsid or "oauth_bridge_fsid",
                    )
                    return {
                        "ok": True,
                        "status": "ready",
                        "snlm0e": bridge_token,
                        "cfb2h": cfb2h,
                        "fsid": fsid or "oauth_bridge_fsid",
                        "email": linked["email"],
                        "detected_tier": linked["tier"],
                        "available_models": _default_node_models_list(),
                    }

                return {
                    "ok": False,
                    "status": "expired",
                    "error": "Không tìm thấy CSRF token SNlM0e trên gemini.google.com/app (Cookie hết hạn hoặc chưa đăng nhập).",
                }

            scraped = scrape_models_and_tier_from_html(html)
            scraped_email = scraped.get("email") or ""
            linked = self._resolve_linked_google_account(node_id, email_hint=scraped_email)
            tier_rank = {"free": 0, "pro": 1, "ultra": 2}
            scraped_tier = str(scraped.get("detected_tier") or "free").lower()
            linked_tier = str(linked.get("tier") or "free").lower() if linked else "free"
            best_tier = linked_tier if tier_rank.get(linked_tier, 0) > tier_rank.get(scraped_tier, 0) else scraped_tier

            self.save_session(
                node_id=node_id,
                cookies=cookies,
                snlm0e=snlm0e,
                cfb2h=cfb2h,
                fsid=fsid,
            )

            return {
                "ok": True,
                "status": "ready",
                "snlm0e": snlm0e,
                "cfb2h": cfb2h,
                "fsid": fsid,
                "email": scraped_email or (linked.get("email") if linked else None),
                "detected_tier": best_tier,
                "available_models": scraped.get("models") or _default_node_models_list(),
            }
        except Exception as e:
            logger.warning("Gemini Web handshake failed for %s: %s", node_id, e)
            return {
                "ok": False,
                "status": "error",
                "error": str(e),
            }
        finally:
            if close_client:
                await http_client.aclose()

    def discover_cookies_from_local_browser_profiles(
        self,
        include_system_profiles: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Auto-discover `.google.com` cookies & Google sessions from Flow, Camofox, Browser SQLite, and OAuth Pool."""
        discovered_by_key: Dict[str, Dict[str, Any]] = {}

        if include_system_profiles is None:
            try:
                include_system_profiles = self.hermes_dir.resolve() == get_hermes_dir().resolve()
            except Exception:
                include_system_profiles = False

        # Read default Flow email/display_name from flow_token.json or flow_accounts.json if present
        flow_default_email = ""
        flow_default_name = ""
        for rel in ("auth/flow_token.json", "flow_token.json", "auth/flow_accounts.json"):
            ff = self.hermes_dir / rel
            if ff.is_file():
                try:
                    fdata = json.loads(ff.read_text(encoding="utf-8"))
                    if isinstance(fdata, dict):
                        user_obj = fdata.get("user") if isinstance(fdata.get("user"), dict) else {}
                        em = str(user_obj.get("email") or fdata.get("email") or "").strip().lower()
                        nm = str(user_obj.get("name") or fdata.get("name") or "").strip()
                        if not em and isinstance(fdata.get("accounts"), dict):
                            for acc_v in fdata["accounts"].values():
                                if isinstance(acc_v, dict) and acc_v.get("email"):
                                    em = str(acc_v["email"]).strip().lower()
                                    nm = str(acc_v.get("label") or "").strip()
                                    break
                        if em and not flow_default_email:
                            flow_default_email = em
                        if nm and not flow_default_name:
                            flow_default_name = nm
                except Exception:
                    pass

        # 1. Check JSON session & Playwright storage-state files
        candidate_json_files: List[Path] = []
        for fname in ("flow_storage_state.json", "flow_session.json", "storage-state.json"):
            fpath = self.hermes_dir / fname
            if fpath.is_file():
                candidate_json_files.append(fpath)

        flow_sess_dir = self.hermes_dir / "flow_sessions"
        if flow_sess_dir.is_dir():
            candidate_json_files.extend(flow_sess_dir.glob("*.json"))

        local_camofox = self.hermes_dir / "camofox" / "profiles"
        if local_camofox.is_dir():
            candidate_json_files.extend(local_camofox.glob("*/storage-state.json"))

        if include_system_profiles:
            sys_camofox = Path.home() / ".camofox" / "profiles"
            if sys_camofox.is_dir():
                candidate_json_files.extend(sys_camofox.glob("*/storage-state.json"))

        for jf in candidate_json_files:
            try:
                raw_text = jf.read_text(encoding="utf-8")
                data = json.loads(raw_text)
                if not isinstance(data, dict):
                    continue
                email = str(data.get("email") or data.get("user_email") or flow_default_email or "").strip().lower()
                raw_cookie_str = str(data.get("cookie") or data.get("cookies_str") or "")
                cookies_dict = parse_flexible_cookie_input(raw_cookie_str)
                if isinstance(data.get("cookies"), dict):
                    cookies_dict.update({str(k): str(v) for k, v in data["cookies"].items() if v})
                elif isinstance(data.get("cookies"), list):
                    parsed_from_state = parse_flexible_cookie_input(raw_text)
                    cookies_dict.update(parsed_from_state)

                if cookies_dict.get("__Secure-1PSID"):
                    dedup_key = email or f"psid:{cookies_dict['__Secure-1PSID'][:24]}"
                    if dedup_key not in discovered_by_key:
                        discovered_by_key[dedup_key] = {
                            "source": f"browser_state:{jf.name}",
                            "email": email,
                            "display_name": flow_default_name if email == flow_default_email else "",
                            "cookies": cookies_dict,
                        }
            except Exception:
                pass

        # 2. Check unencrypted Chromium/Firefox SQLite cookies in flow_browser_session & Camofox
        browser_dir = self.hermes_dir / "flow_browser_session"
        if browser_dir.is_dir():
            for sq_path in browser_dir.rglob("Cookies"):
                try:
                    conn = sqlite3.connect(f"file:{sq_path}?mode=ro", uri=True)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT name, value, host_key FROM cookies WHERE host_key LIKE '%google.com%' AND value != ''"
                    )
                    rows = cur.fetchall()
                    conn.close()
                    ck_map: Dict[str, str] = {}
                    for r_name, r_val, r_host in rows:
                        if not r_name or not r_val:
                            continue
                        host_l = str(r_host or "").lower()
                        if host_l in (".google.com", "google.com", "gemini.google.com") or str(r_name) not in ck_map:
                            ck_map[str(r_name)] = str(r_val)
                    if ck_map.get("__Secure-1PSID"):
                        dedup_key = flow_default_email or f"psid:{ck_map['__Secure-1PSID'][:24]}"
                        if dedup_key not in discovered_by_key:
                            discovered_by_key[dedup_key] = {
                                "source": "flow_browser_session",
                                "email": flow_default_email,
                                "display_name": flow_default_name,
                                "cookies": ck_map,
                            }
                except Exception:
                    pass

        # 3. Check authenticated Google OAuth Pool accounts (antigravity_tokens.json)
        for rel in ("auth/antigravity_tokens.json", "antigravity_tokens.json"):
            tf = self.hermes_dir / rel
            if not tf.is_file():
                continue
            try:
                tdata = json.loads(tf.read_text(encoding="utf-8"))
                if not isinstance(tdata, dict):
                    continue
                raw_accs = tdata.get("accounts")
                accounts = list(raw_accs.values()) if isinstance(raw_accs, dict) else (raw_accs if isinstance(raw_accs, list) else [])
                for acc in accounts:
                    if not isinstance(acc, dict):
                        continue
                    em = str(acc.get("email") or "").strip().lower()
                    if not em:
                        continue
                    tier_raw = f"{acc.get('tier_id') or ''} {acc.get('plan_name') or ''} {acc.get('plan_type') or ''}".lower()
                    tier = "ultra" if "ultra" in tier_raw else ("pro" if "pro" in tier_raw else "free")
                    tier_label = "Google AI Ultra" if tier == "ultra" else ("Google AI Pro" if tier == "pro" else "Free")
                    disp = f"{em.split('@')[0]} ({tier_label})"

                    if em in discovered_by_key:
                        discovered_by_key[em]["detected_tier"] = tier
                        discovered_by_key[em]["linked_oauth_account_id"] = em
                        if not discovered_by_key[em].get("display_name"):
                            discovered_by_key[em]["display_name"] = disp
                    else:
                        discovered_by_key[em] = {
                            "source": "antigravity_oauth_pool",
                            "email": em,
                            "display_name": disp,
                            "detected_tier": tier,
                            "linked_oauth_account_id": em,
                            "cookies": {
                                "__Secure-1PSID": f"oauth_linked_{em}",
                                "__Secure-1PSIDTS": f"oauth_ts_{int(time.time())}",
                            },
                        }
            except Exception:
                pass

        return list(discovered_by_key.values())

