"""Antigravity & Google Flow Dashboard Plugin API.

Mounted at /api/plugins/antigravity/ by the Hermes Dashboard plugin system.
Provides comprehensive endpoints for:
1. Daemon management (status, start, stop, restart, auto-wake).
2. Google Antigravity OAuth Account Pool & rotation strategy.
3. Live Model Discovery & Quota summary (Gemini 3.7, Claude Sonnet/Opus, GPT-OSS).
4. Google Flow Veo 3.1 & Omni 1.1 video generator (1-Click handshake, credits, models).
5. AI Image Generation configuration & live test playground.
6. System Doctor diagnostics & bridge daemon log streamer.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Ensure bridge is on sys.path
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent
for _p in (str(_PLUGIN_ROOT), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("hermes.plugins.antigravity.dashboard_api")

router = APIRouter()


# ─── Data Schemas ─────────────────────────────────────────────────────────────

class HandshakeStartResponse(BaseModel):
    ok: bool = True
    session_id: str
    status: str
    expires_at: float
    message: str


class HandshakePollResponse(BaseModel):
    session_id: str
    status: str  # pending, completed, error, timeout, cancelled
    email: Optional[str] = None
    error: Optional[str] = None
    connected: bool = False


class FlowStatusResponse(BaseModel):
    connected: bool
    email: Optional[str] = None
    user_name: Optional[str] = None
    user_image: Optional[str] = None
    is_expired: bool
    expires_in_seconds: int
    expires_at: Optional[str] = None
    has_session_cookie: bool
    credits: Optional[int] = None
    token_preview: Optional[str] = None
    status_label: str


class DisconnectResponse(BaseModel):
    ok: bool
    message: str


class RefreshResponse(BaseModel):
    ok: bool
    message: str
    status: FlowStatusResponse


class DaemonStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    port: int = 8100
    host: str = "127.0.0.1"
    uptime_seconds: Optional[float] = None
    log_file: str
    pid_file: str


class DaemonControlRequest(BaseModel):
    action: str  # start, stop, restart


class DaemonControlResponse(BaseModel):
    ok: bool
    message: str
    status: DaemonStatusResponse


class AccountItem(BaseModel):
    model_config = {"protected_namespaces": ()}
    email: str
    role: str = "all"
    status: str = "active"
    project_id: Optional[str] = None
    expires_at: float = 0.0
    is_expired: bool = False
    is_available: bool = True
    is_active: bool = False
    cooldown_seconds: int = 0
    usage_count: int = 0
    plan_name: str = "Free Tier"
    plan_type: str = "free"  # "ultra" | "pro" | "free"
    tier_id: Optional[str] = ""
    quota_summary: Optional[Dict[str, Any]] = None
    model_cooldowns: Optional[Dict[str, int]] = None
    health_score: Optional[float] = None


class AccountPoolResponse(BaseModel):
    ok: bool
    count: int
    active_email: Optional[str] = None
    strategy: str
    mode: str
    accounts: List[AccountItem]


class AccountActionRequest(BaseModel):
    email: str


class AccountStrategyRequest(BaseModel):
    strategy: str  # fill_first, round_robin, least_used, sharded


class AccountRoleRequest(BaseModel):
    email: str
    role: str  # all, llm, image_gen


class FlowAccountItem(BaseModel):
    id: str
    user_id: str
    email: str
    label: str = ""
    status: str = "active"
    is_available: bool = True
    is_active: bool = False
    total_creations: int = 0
    last_used: Optional[float] = None
    cooldown_minutes: int = 0


class FlowAccountPoolResponse(BaseModel):
    ok: bool
    count: int
    active_id: str
    accounts: List[FlowAccountItem]


class FlowAccountActionRequest(BaseModel):
    account_id: str


class VideoModelItem(BaseModel):
    id: str
    display: str
    tier: str
    credits: int
    speed: str
    strengths: str
    duration: str
    is_active: bool = False


class VideoModelSetRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str


class ImageConfigRequest(BaseModel):
    aspect_ratio: Optional[str] = None
    provider: Optional[str] = None


class ImageGenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "16:9"


class DoctorCheckItem(BaseModel):
    id: str
    label: str
    status: str  # ok, warn, error, info
    message: str
    detail: Optional[str] = None


class DoctorReportResponse(BaseModel):
    all_good: bool
    score: int
    checks: List[DoctorCheckItem]


# ─── Helper Functions ────────────────────────────────────────────────────────

def _get_hermes_dir() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except Exception:
        pass
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home() / ".hermes"


def _get_auth_service():
    try:
        from bridge.flow.flow_auth_service import FlowAuthService
        return FlowAuthService.get_instance()
    except ImportError:
        try:
            from tools.antigravity_bridge.flow.flow_auth_service import FlowAuthService
            return FlowAuthService.get_instance()
        except ImportError:
            raise HTTPException(status_code=500, detail="FlowAuthService could not be imported.")


def _get_refresh_daemon():
    try:
        from bridge.flow.flow_refresh_daemon import FlowRefreshDaemon
        return FlowRefreshDaemon.get_instance()
    except ImportError:
        try:
            from tools.antigravity_bridge.flow.flow_refresh_daemon import FlowRefreshDaemon
            return FlowRefreshDaemon.get_instance()
        except ImportError:
            raise HTTPException(status_code=500, detail="FlowRefreshDaemon could not be imported.")


def _get_ag_auth_manager():
    try:
        from tools.antigravity_bridge.auth import AntigravityAuthManager
        return AntigravityAuthManager()
    except ImportError:
        try:
            from bridge.auth import AntigravityAuthManager
            return AntigravityAuthManager()
        except ImportError:
            raise HTTPException(status_code=500, detail="AntigravityAuthManager could not be imported.")


def _get_ag_account_pool():
    # Try canonical tools.antigravity_bridge with method check
    try:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
        if hasattr(AntigravityAccountPoolManager, "get_account_quota_buckets"):
            return AntigravityAccountPoolManager()
    except ImportError:
        pass
    # Try bridge with method check
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
        if hasattr(AntigravityAccountPoolManager, "get_account_quota_buckets"):
            return AntigravityAccountPoolManager()
    except ImportError:
        pass
    # Final fallback
    try:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
        return AntigravityAccountPoolManager()
    except ImportError:
        try:
            from bridge.account_pool import AntigravityAccountPoolManager
            return AntigravityAccountPoolManager()
        except ImportError:
            raise HTTPException(status_code=500, detail="AntigravityAccountPoolManager could not be imported.")


def _get_flow_account_pool():
    try:
        from bridge.flow.account_pool import FlowAccountPoolManager
        return FlowAccountPoolManager()
    except ImportError:
        try:
            from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager
            return FlowAccountPoolManager()
        except ImportError:
            raise HTTPException(status_code=500, detail="FlowAccountPoolManager could not be imported.")


def _get_server_module():
    try:
        import tools.antigravity_bridge.server as srv
        return srv
    except ImportError:
        try:
            import bridge.server as srv
            return srv
        except ImportError:
            raise HTTPException(status_code=500, detail="Bridge server module could not be imported.")


# ─── Daemon Management Endpoints ─────────────────────────────────────────────

@router.get("/daemon/status", response_model=DaemonStatusResponse)
async def get_daemon_status():
    """Return live status of the local Antigravity Bridge Daemon."""
    srv = _get_server_module()
    port = srv.DEFAULT_BRIDGE_PORT
    host = srv.DEFAULT_BRIDGE_HOST
    pid_file = srv.get_pid_file()
    log_file = srv.get_log_file()

    running = srv.is_server_running(host, port)
    pid: Optional[int] = None
    uptime: Optional[float] = None

    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            mtime = pid_file.stat().st_mtime
            if running:
                uptime = max(0.0, time.time() - mtime)
        except Exception:
            pid = None

    return DaemonStatusResponse(
        running=running,
        pid=pid,
        port=port,
        host=host,
        uptime_seconds=uptime,
        log_file=str(log_file),
        pid_file=str(pid_file),
    )


@router.post("/daemon/control", response_model=DaemonControlResponse)
async def control_daemon(req: DaemonControlRequest):
    """Start, stop, or restart the Antigravity Bridge Daemon."""
    action = req.action.lower().strip()
    srv = _get_server_module()
    port = srv.DEFAULT_BRIDGE_PORT
    host = srv.DEFAULT_BRIDGE_HOST
    pid_file = srv.get_pid_file()
    log_file = srv.get_log_file()

    def _stop_proc() -> bool:
        if not pid_file.is_file():
            return True
        try:
            p = int(pid_file.read_text(encoding="utf-8").strip())
            if p > 0:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
                else:
                    os.kill(p, signal.SIGTERM)
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)
        time.sleep(0.5)
        return not srv.is_server_running(host, port)

    def _start_proc() -> bool:
        if srv.is_server_running(host, port):
            return True
        log_fd = open(log_file, "a", encoding="utf-8")
        cmd = [
            sys.executable,
            "-u",
            "-c",
            f"import sys; sys.path.insert(0, {repr(str(_PLUGIN_ROOT))}); sys.path.insert(0, {repr(str(_REPO_ROOT))}); "
            f"from tools.antigravity_bridge.server import run_server; run_server(host={repr(str(host))}, port={int(port)})",
        ]
        flags = 0
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200 | 0x01000000
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_PLUGIN_ROOT),
                stdout=log_fd,
                stderr=log_fd,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
                env=env,
            )
            pid_file.write_text(str(proc.pid), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to spawn daemon: {e}")
            return False
        finally:
            try:
                log_fd.close()
            except Exception:
                pass

        deadline = time.time() + 8.0
        while time.time() < deadline:
            if srv.is_server_running(host, port):
                return True
            time.sleep(0.3)
        return False

    if action == "stop":
        _stop_proc()
        msg = "Bridge Daemon đã dừng."
    elif action == "start":
        ok = _start_proc()
        msg = "Bridge Daemon đã khởi động thành công." if ok else "Khởi động daemon thất bại (timeout/error)."
    elif action == "restart":
        _stop_proc()
        ok = _start_proc()
        msg = "Bridge Daemon đã khởi động lại thành công." if ok else "Khởi động lại daemon thất bại."
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    st = await get_daemon_status()
    return DaemonControlResponse(ok=st.running if action != "stop" else True, message=msg, status=st)


# ─── Antigravity OAuth Account Pool Endpoints ───────────────────────────────

@router.get("/accounts", response_model=AccountPoolResponse)
async def get_accounts():
    """List all accounts in the Antigravity OAuth pool."""
    pool = _get_ag_account_pool()
    accounts = pool.list_accounts()
    active = pool.get_active_account()
    strategy = pool.get_rotation_strategy()

    now = time.time()
    items: List[AccountItem] = []
    for acc in accounts:
        cd = max(0, int(acc.exhausted_until - now)) if acc.exhausted_until else 0
        role = str(getattr(acc, "role", getattr(acc, "assigned_role", "all")) or "all")
        usage_count = getattr(acc, "request_count", getattr(acc, "total_requests", 0))
        tier_id = getattr(acc, "tier_id", "") or ""
        plan_type = getattr(acc, "computed_plan_type", getattr(acc, "plan_type", "free")) or "free"
        plan_name = getattr(acc, "display_plan_name", getattr(acc, "plan_name", "")) or ""
        t_low = tier_id.lower()
        p_low = plan_name.lower()
        if "ultra" in t_low or "ultra" in p_low:
            plan_type = "ultra"
            plan_name = plan_name or "Google AI Ultra"
        elif "pro" in t_low or "pro" in p_low:
            plan_type = "pro"
            plan_name = plan_name or "Google AI Pro"
        elif not plan_name or plan_name.lower() in {"free", "free tier", "antigravity starter quota"}:
            plan_name = "Free Tier"
            plan_type = "free"
        quota_summary = getattr(acc, "quota_summary", None) or None
        raw_mc = getattr(acc, "model_cooldowns", None)
        model_cds: Optional[Dict[str, int]] = None
        if isinstance(raw_mc, dict) and raw_mc:
            active_mc = {
                str(k): max(0, int(float(v) - now))
                for k, v in raw_mc.items()
                if v is not None and float(v) > now
            }
            if active_mc:
                model_cds = active_mc
        health_score: Optional[float] = None
        if hasattr(acc, "compute_routing_health_score"):
            try:
                in_flight = pool.get_in_flight_count(acc.email) if hasattr(pool, "get_in_flight_count") else 0
                health_score = float(acc.compute_routing_health_score("", in_flight=in_flight))
            except Exception:
                health_score = None
        items.append(AccountItem(
            email=acc.email,
            role=role,
            status=acc.status,
            project_id=acc.project_id,
            expires_at=acc.expires_at,
            is_expired=acc.is_expired,
            is_available=acc.is_available,
            is_active=bool(active and active.email == acc.email),
            cooldown_seconds=cd,
            usage_count=usage_count,
            plan_name=plan_name,
            plan_type=plan_type,
            tier_id=tier_id,
            quota_summary=quota_summary,
            model_cooldowns=model_cds,
            health_score=health_score,
        ))

    items.sort(
        key=lambda item: (
            0 if (item.is_active and item.status != "disabled")
            else 1 if (item.is_available and item.status != "disabled")
            else 2 if item.status != "disabled"
            else 3,
            item.email,
        )
    )

    mode = "Multi-Account Sharded Pool" if len(accounts) >= 2 else "Single-Account Resilience Mode"
    return AccountPoolResponse(
        ok=True,
        count=len(items),
        active_email=active.email if active else None,
        strategy=strategy,
        mode=mode,
        accounts=items,
    )


@router.post("/accounts/switch")
async def switch_account(req: AccountActionRequest):
    """Switch the active account in the Antigravity pool."""
    pool = _get_ag_account_pool()
    email = req.email.strip().lower()
    acc = pool.get_account(email)
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account '{email}' not found.")
    pool.set_active_account(email)
    return {"ok": True, "message": f"Đã chuyển tài khoản hoạt động sang: {email}"}


@router.post("/accounts/remove")
async def remove_account(req: AccountActionRequest):
    """Remove an account from the Antigravity pool."""
    pool = _get_ag_account_pool()
    email = req.email.strip().lower()
    removed = pool.remove_account(email)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Account '{email}' not found.")
    return {"ok": True, "message": f"Đã xóa tài khoản: {email}"}


@router.post("/accounts/strategy")
async def set_account_strategy(req: AccountStrategyRequest):
    """Configure rotation strategy (fill_first, round_robin, least_used, sharded)."""
    pool = _get_ag_account_pool()
    strat = req.strategy.strip().lower()
    allowed = {"fill_first", "round_robin", "least_used", "sharded"}
    if strat not in allowed:
        raise HTTPException(status_code=400, detail=f"Strategy must be one of: {allowed}")
    pool.set_rotation_strategy(strat)
    return {"ok": True, "message": f"Đã cập nhật chiến lược xoay vòng: {strat.upper()}"}


@router.post("/accounts/role")
async def set_account_role(req: AccountRoleRequest):
    """Assign service role (all, llm, image_gen) to an account."""
    pool = _get_ag_account_pool()
    email = req.email.strip().lower()
    role = req.role.strip().lower()
    allowed = {"all", "llm", "image_gen"}
    if role not in allowed:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {allowed}")
    if not pool.set_account_role(email, role):
        raise HTTPException(status_code=404, detail=f"Account '{email}' not found.")
    return {"ok": True, "message": f"Đã gán vai trò '{role}' cho tài khoản {email}"}


@router.post("/accounts/check-unlock")
async def check_account_unlock(req: AccountActionRequest):
    """Live-probe Google Code Assist to check if a disabled account (or 'all' disabled accounts) has been unlocked."""
    auth_mgr = _get_ag_auth_manager()
    pool = _get_ag_account_pool()
    target = (req.email or "").strip().lower()
    loop = asyncio.get_event_loop()

    if target == "all":
        candidates = [a.email for a in pool.list_accounts() if a.status in {"disabled", "cooling_down", "exhausted"}]
        if not candidates:
            return {
                "ok": True,
                "unlocked_count": 0,
                "results": [],
                "message": "Tất cả tài khoản đều đang ở trạng thái SẴN SÀNG (không có tài khoản nào bị khóa).",
            }
        results = []
        unlocked_emails = []
        for em in candidates:
            res = await loop.run_in_executor(None, auth_mgr.probe_account_unlock_status, em)
            results.append(res)
            if res.get("unlocked"):
                unlocked_emails.append(em)
        if unlocked_emails:
            msg = f"Đã mở khóa & khôi phục {len(unlocked_emails)}/{len(candidates)} tài khoản: {', '.join(unlocked_emails)}!"
        else:
            msg = f"Đã kiểm tra {len(candidates)} tài khoản bị khóa: Google vẫn chưa mở khóa (403 TOS_VIOLATION)."
        return {
            "ok": True,
            "unlocked_count": len(unlocked_emails),
            "unlocked_emails": unlocked_emails,
            "results": results,
            "message": msg,
        }

    res = await loop.run_in_executor(None, auth_mgr.probe_account_unlock_status, target)
    return res


@router.post("/accounts/refresh-plan-quota")
async def refresh_plan_quota(req: Optional[AccountActionRequest] = None):
    """Live-query Google Code Assist for Plan (Ultra/Pro/Free) and Quota telemetry.
    If req is omitted or req.email is 'all' / empty, refreshes all active/available accounts in the pool.
    """
    pool = _get_ag_account_pool()
    target = (req.email.strip().lower() if (req and req.email) else "all")
    loop = asyncio.get_event_loop()

    if target == "all" or not target:
        accounts = pool.list_accounts()
        candidates = [a.email for a in accounts if a.status != "disabled"]
        if not candidates and accounts:
            candidates = [accounts[0].email]
        if not candidates:
            return {"ok": False, "message": "Không có tài khoản nào trong pool để làm mới."}

        results = []
        for em in candidates:
            r = await loop.run_in_executor(None, pool.refresh_account_plan_and_quota, em)
            results.append(r)

        updated_plans = [f"{r['email']}: {r.get('plan_name', 'Free Tier')}" for r in results if r.get("ok")]
        return {
            "ok": True,
            "refreshed_count": len(results),
            "results": results,
            "message": f"Đã quét và cập nhật gói & quota cho {len(results)} tài khoản: {', '.join(updated_plans)}",
        }
    else:
        res = await loop.run_in_executor(None, pool.refresh_account_plan_and_quota, target)
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("message", "Quét plan/quota thất bại."))
        return res


_PKCE_SESSIONS: Dict[str, Dict[str, Any]] = {}
_OAUTH_LISTENER_STARTED = False
_OAUTH_LISTENER_LOCK = threading.Lock()


def _get_pkce_store_file() -> Path:
    try:
        from hermes_constants import get_hermes_dir
        base = Path(get_hermes_dir())
    except Exception:
        base = Path.home() / ".hermes"
    auth_dir = base / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir / "pkce_sessions.json"


def _load_pkce_sessions() -> Dict[str, Dict[str, Any]]:
    global _PKCE_SESSIONS
    now = time.time()
    try:
        fpath = _get_pkce_store_file()
        if fpath.is_file():
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for sid, s in data.items():
                    if isinstance(s, dict) and s.get("expires_at", 0) > now:
                        if sid not in _PKCE_SESSIONS or s.get("completed"):
                            _PKCE_SESSIONS[sid] = s
    except Exception:
        pass
    expired = [sid for sid, s in list(_PKCE_SESSIONS.items()) if s.get("expires_at", 0) < now]
    for sid in expired:
        _PKCE_SESSIONS.pop(sid, None)
    return _PKCE_SESSIONS


def _save_pkce_sessions() -> None:
    try:
        fpath = _get_pkce_store_file()
        fpath.write_text(json.dumps(_PKCE_SESSIONS, indent=2), encoding="utf-8")
    except Exception:
        pass


def _resolve_pkce_session(session_id: str, callback_url: str = "") -> Optional[Dict[str, Any]]:
    """Resolve PKCE session by session_id, or by the OAuth state= parameter inside callback_url, or newest session."""
    sessions = _load_pkce_sessions()
    raw = (callback_url or "").strip()
    extracted_state = None
    if raw:
        try:
            import urllib.parse
            norm = raw if "://" in raw else ("http://" + raw if ("localhost" in raw or "127.0.0.1" in raw) else raw)
            parsed = urllib.parse.urlparse(norm)
            qs = urllib.parse.parse_qs(parsed.query)
            if not qs and "?" in raw:
                qs = urllib.parse.parse_qs(raw.split("?", 1)[-1])
            extracted_state = (qs.get("state") or [None])[0]
        except Exception:
            pass

    if extracted_state:
        for s in sessions.values():
            if s.get("state") == extracted_state:
                return s

    if session_id and session_id in sessions:
        return sessions[session_id]

    # Fallback: most recently created non-completed session
    candidates = [s for s in sessions.values() if not s.get("completed")]
    if candidates:
        candidates.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
        return candidates[0]
    return None


def _complete_pkce_and_sync_sync(session: Dict[str, Any], callback_or_code: str) -> Dict[str, Any]:
    """Synchronous worker that exchanges OAuth code, updates account pool, probes plan/quota, and syncs Gemini Web."""
    auth_mgr = _get_ag_auth_manager()
    # If matched via fallback session where state might differ or raw code was pasted, only enforce state if it matches
    expected_state = session.get("state")
    if expected_state and "state=" in callback_or_code and expected_state not in callback_or_code:
        expected_state = None

    creds = auth_mgr.complete_pkce_auth_session(
        callback_or_code=callback_or_code,
        code_verifier=session["code_verifier"],
        redirect_uri=session["redirect_uri"],
        expected_state=expected_state,
    )
    pool = _get_ag_account_pool()
    acc = pool.add_or_update_account(creds, reset_status=True)
    pool.set_active_account(acc.email)
    try:
        pool.refresh_account_plan_and_quota(acc.email)
    except Exception:
        pass
    try:
        gweb_pool = _get_gemini_web_pool()
        asyncio.run(_auto_sync_gemini_web_pool(gweb_pool))
    except Exception:
        pass

    session["completed"] = True
    session["email"] = acc.email
    session["project_id"] = creds.project_id
    session["completed_at"] = time.time()
    _PKCE_SESSIONS[session["session_id"]] = session
    _save_pkce_sessions()
    return {
        "ok": True,
        "email": acc.email,
        "project_id": creds.project_id,
        "message": f"Đăng nhập Google thành công & đã tự động gắn vào Bể OAuth + Gemini Web: {acc.email}",
    }


def _ensure_local_oauth_callback_listener(port: int = 51121) -> None:
    """Start a background HTTP listener on 127.0.0.1:51121 so local/tunneled OAuth callbacks complete with 0 copy-paste."""
    global _OAUTH_LISTENER_STARTED
    with _OAUTH_LISTENER_LOCK:
        if _OAUTH_LISTENER_STARTED:
            return
        try:
            import http.server

            class _CallbackHandler(http.server.BaseHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass

                def do_GET(self):
                    full_url = f"http://localhost:{port}{self.path}"
                    sess = _resolve_pkce_session("", full_url)
                    if not sess or "code=" not in self.path:
                        self.send_response(400)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(b"<html><body><h3>Missing OAuth code or expired session.</h3></body></html>")
                        return
                    try:
                        res = _complete_pkce_and_sync_sync(sess, full_url)
                        email_str = res.get("email") or ""
                        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Đăng nhập thành công</title></head>
                        <body style="background:#090b10;color:#e4e4e7;font-family:sans-serif;text-align:center;padding:48px 20px;">
                        <div style="max-width:460px;margin:0 auto;background:#12151e;border:1px solid rgba(16,185,129,0.4);border-radius:12px;padding:28px;">
                        <h2 style="color:#34d399;margin-top:0;">✅ Đăng nhập Google thành công!</h2>
                        <p style="font-size:14px;color:#a1a1aa;">Tài khoản <strong style="color:#fff;">{email_str}</strong> đã được tự động nạp vào Bể OAuth & Gemini Web Pool.</p>
                        <p style="font-size:12px;color:#71717a;">Cửa sổ này sẽ tự động đóng sau 1 giây...</p>
                        </div><script>setTimeout(function(){{window.close();}},1200);</script></body></html>"""
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(html.encode("utf-8"))
                    except Exception as e:
                        self.send_response(500)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(f"<html><body><h3>Lỗi xác thực OAuth: {e}</h3></body></html>".encode("utf-8"))

            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _CallbackHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            _OAUTH_LISTENER_STARTED = True
        except Exception:
            pass


class AccountLoginSubmitRequest(BaseModel):
    session_id: Optional[str] = ""
    callback_url: str


@router.post("/accounts/login-start")
async def start_oauth_login():
    """Create a Google OAuth PKCE session and return auth_url immediately for mobile/remote or local browser."""
    auth_mgr = _get_ag_auth_manager()
    try:
        _load_pkce_sessions()
        _ensure_local_oauth_callback_listener()
        session = auth_mgr.create_pkce_auth_session()
        _PKCE_SESSIONS[session["session_id"]] = session
        _save_pkce_sessions()
        return {
            "ok": True,
            "session_id": session["session_id"],
            "state": session["state"],
            "auth_url": session["auth_url"],
            "redirect_uri": session["redirect_uri"],
            "message": "Đã tạo liên kết đăng nhập Google OAuth PKCE.",
        }
    except Exception as e:
        logger.error(f"OAuth login-start failed: {e}")
        return {"ok": False, "error": str(e), "message": f"Không thể khởi tạo OAuth: {e}"}


@router.get("/accounts/login-poll/{session_id}")
async def poll_oauth_login(session_id: str):
    """Poll whether a PKCE login session has completed automatically via the local callback listener or another tab."""
    sessions = _load_pkce_sessions()
    s = sessions.get(session_id)
    if s and s.get("completed"):
        return {
            "ok": True,
            "completed": True,
            "email": s.get("email") or "",
            "project_id": s.get("project_id") or "",
            "message": f"Đăng nhập Google thành công: {s.get('email')}",
        }
    return {"ok": True, "completed": False}


@router.post("/accounts/login-submit")
async def submit_oauth_login(req: AccountLoginSubmitRequest):
    """Complete Google OAuth PKCE login using the callback URL or code pasted from mobile/browser."""
    session = _resolve_pkce_session(req.session_id or "", req.callback_url)
    if not session:
        return {
            "ok": False,
            "message": "Phiên đăng nhập đã hết hạn hoặc không tồn tại. Vui lòng bấm Mở Trang Đăng Nhập Google lại.",
        }
    if session.get("completed") and session.get("email"):
        return {
            "ok": True,
            "email": session["email"],
            "project_id": session.get("project_id") or "",
            "message": f"Đăng nhập Google thành công & đã tự động gắn vào Bể Gemini Web: {session['email']}",
        }

    loop = asyncio.get_event_loop()
    try:
        res = await loop.run_in_executor(None, _complete_pkce_and_sync_sync, session, req.callback_url)
        try:
            gweb_pool = _get_gemini_web_pool()
            await _auto_sync_gemini_web_pool(gweb_pool)
        except Exception:
            pass
        return res
    except Exception as e:
        logger.error(f"OAuth login-submit failed: {e}")
        return {"ok": False, "error": str(e), "message": f"Xác thực OAuth thất bại: {e}"}



# ─── Live Models Discovery & Quota Summary ───────────────────────────────────

@router.get("/antigravity/models")
async def get_antigravity_models(refresh: bool = False):
    """List models dynamically discovered from Antigravity IDE / Code Assist."""
    try:
        try:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
        except ImportError:
            from bridge.models import ModelDiscoveryManager
        mgr = ModelDiscoveryManager()
        models = mgr.get_discovered_models(force_refresh=refresh)
        res = []
        for m in models:
            res.append({
                "id": m.id,
                "display_name": m.display_name,
                "quota_fraction": m.quota_fraction,
                "supports_thinking": m.supports_thinking,
                "thinking_budget": m.thinking_budget,
                "max_tokens": m.max_tokens,
                "recommended": m.recommended,
            })
        return {"ok": True, "count": len(res), "models": res}
    except Exception as e:
        logger.error(f"Failed to discover models: {e}")
        return {"ok": False, "count": 0, "models": [], "error": str(e)}


@router.get("/antigravity/quota")
async def get_antigravity_quota(email: Optional[str] = None, refresh: bool = False):
    """Fetch live quota buckets and rate limit summary from Code Assist API for a specific account (or active account)."""
    try:
        pool = _get_ag_account_pool()
        target = (email or "").strip().lower()
        if not target or target == "active":
            active = pool.get_active_account()
            target = active.email if active else ""

        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(None, pool.get_account_quota_buckets, target, refresh)
        return {"ok": True, "email": target, "summary": summary}
    except Exception as e:
        logger.error(f"Failed to fetch quota for {email}: {e}")
        return {"ok": False, "email": email or "", "summary": {}, "error": str(e)}


# ─── Google Flow Video Endpoints ─────────────────────────────────────────────

@router.get("/flow/status", response_model=FlowStatusResponse)
async def get_flow_status():
    """Return live status of Google Flow connection."""
    svc = _get_auth_service()
    st = svc.get_status()
    return FlowStatusResponse(**st)


@router.post("/flow/login-start", response_model=HandshakeStartResponse)
async def start_flow_login(timeout: int = Query(default=180, ge=30, le=600)):
    """Initiate 1-Click Visible Handshake login in background."""
    svc = _get_auth_service()
    session = svc.start_handshake(timeout_seconds=timeout)
    return HandshakeStartResponse(
        ok=True,
        session_id=session.session_id,
        status=session.status,
        expires_at=session.expires_at,
        message="Cửa sổ trình duyệt đã được khởi chạy trên màn hình của bạn. Vui lòng nhấn vào tài khoản Google để hoàn tất kết nối.",
    )


@router.get("/flow/login-poll/{session_id}", response_model=HandshakePollResponse)
async def poll_flow_login(session_id: str):
    """Poll progress of an ongoing 1-Click Handshake session."""
    svc = _get_auth_service()
    session = svc.get_handshake_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Handshake session not found or expired.")

    connected = session.status == "completed"
    return HandshakePollResponse(
        session_id=session.session_id,
        status=session.status,
        email=session.email,
        error=session.error_message,
        connected=connected,
    )


@router.post("/flow/login-cancel/{session_id}")
async def cancel_flow_login(session_id: str):
    """Cancel an active 1-Click Handshake session."""
    svc = _get_auth_service()
    success = svc.cancel_handshake(session_id)
    return {"ok": success, "message": "Phiên đăng nhập đã bị hủy." if success else "Không tìm thấy phiên cần hủy."}


@router.post("/flow/refresh", response_model=RefreshResponse)
async def refresh_flow_token():
    """Trigger headless background token refresh using the 30-day session cookie."""
    daemon = _get_refresh_daemon()
    success, result = await daemon.ensure_active_token(min_validity_seconds=120)
    svc = _get_auth_service()
    st = svc.get_status()

    if success:
        return RefreshResponse(
            ok=True,
            message="Token Google Flow đã được làm mới ngầm thành công!",
            status=FlowStatusResponse(**st),
        )
    else:
        return RefreshResponse(
            ok=False,
            message=f"Làm mới thất bại: {result}",
            status=FlowStatusResponse(**st),
        )


@router.post("/flow/disconnect", response_model=DisconnectResponse)
async def disconnect_flow():
    """Disconnect Google Flow session and clear tokens."""
    svc = _get_auth_service()
    cleared = svc.disconnect()
    return DisconnectResponse(
        ok=True,
        message="Đã ngắt kết nối Google Flow thành công." if cleared else "Không có phiên đăng nhập nào để ngắt kết nối.",
    )


@router.get("/flow/models")
async def get_flow_models():
    """Return all 5 tiers of Google Flow Veo 3.1 & Omni 1.1 video generation models."""
    try:
        from video_gen.antigravity import VEO_MODELS
    except ImportError:
        VEO_MODELS = [
            {"id": "veo-3.1-lite-free", "display": "Veo 3.1 Lite (Free)", "tier": "100% Miễn Phí", "credits": 0, "speed": "Cực nhanh (~10s)", "duration": "4s", "strengths": "Tạo nháp, xem trước kịch bản, 0 credit"},
            {"id": "veo-3.1-lite", "display": "Veo 3.1 Lite", "tier": "Tiết Kiệm", "credits": 5, "speed": "Nhanh (~15s)", "duration": "6s", "strengths": "Chi phí thấp, kiểm thử ý tưởng"},
            {"id": "omni-1.1-flash", "display": "Omni 1.1 Flash (Mặc Định)", "tier": "Tiêu Chuẩn Cân Bằng", "credits": 6, "speed": "Tối ưu (~20s)", "duration": "10s", "strengths": "Có âm thanh tự nhiên, chuyển động mượt mà"},
            {"id": "veo-3.1-fast", "display": "Veo 3.1 Fast", "tier": "Chất Lượng Cao", "credits": 10, "speed": "Trung bình (~30s)", "duration": "10s", "strengths": "Độ nét cao, ánh sáng chân thực"},
            {"id": "veo-3.1-quality", "display": "Veo 3.1 Quality", "tier": "Điện Ảnh Studio", "credits": 100, "speed": "Kỹ lưỡng (~60s)", "duration": "10s", "strengths": "Chi tiết quang học tối đa, chuẩn studio"},
        ]

    # Resolve active model from config.yaml
    cfg_file = _get_hermes_dir() / "config.yaml"
    current_model = "omni-1.1-flash"
    if cfg_file.is_file():
        try:
            import yaml
            with open(cfg_file, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
            current_model = d.get("video_gen", {}).get("model") or "omni-1.1-flash"
        except Exception:
            pass

    items: List[VideoModelItem] = []
    for m in VEO_MODELS[:5]:
        raw_dur = m.get("duration", "10s")
        dur_str = f"{raw_dur}s" if isinstance(raw_dur, (int, float)) else str(raw_dur)
        items.append(VideoModelItem(
            id=m["id"],
            display=m["display"],
            tier=m.get("tier", ""),
            credits=m.get("credits", 0),
            speed=m.get("speed", ""),
            strengths=m.get("strengths", ""),
            duration=dur_str,
            is_active=(m["id"] == current_model),
        ))

    return {"ok": True, "current_model": current_model, "models": items}


@router.post("/flow/model/set")
async def set_flow_model(req: VideoModelSetRequest):
    """Set default video model in ~/.hermes/config.yaml."""
    target = req.model_id.strip().lower()
    cfg_file = _get_hermes_dir() / "config.yaml"
    try:
        import yaml
        data = {}
        if cfg_file.is_file():
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data.setdefault("video_gen", {})["model"] = target
        data.setdefault("video_gen", {})["provider"] = "antigravity"
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False)
        return {"ok": True, "message": f"Đã cập nhật mô hình video mặc định sang: {target}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể cập nhật config.yaml: {e}")


@router.get("/flow/accounts")
async def get_flow_accounts():
    """List all accounts in the Google Flow multi-account pool."""
    try:
        pool = _get_flow_account_pool()
    except Exception:
        return {"ok": True, "accounts": [], "active_id": "default"}

    accounts = pool.list_accounts()
    active = pool.get_active_account()
    res = [
        {
            "id": a.id,
            "email": a.email,
            "label": a.label,
            "status": a.status,
            "is_available": a.is_available,
            "is_active": bool(active and active.id == a.id),
        }
        for a in accounts
    ]
    return {"ok": True, "count": len(res), "active_id": active.id if active else "default", "accounts": res}


@router.post("/flow/accounts/switch")
async def switch_flow_account(account_id: str = Query(...)):
    """Switch active Google Flow account."""
    try:
        pool = _get_flow_account_pool()
        pool.set_active_account(account_id)
        return {"ok": True, "message": f"Đã đổi tài khoản Google Flow sang: {account_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flow/accounts/remove")
async def remove_flow_account(account_id: str = Query(...)):
    """Remove an account from Google Flow pool."""
    try:
        pool = _get_flow_account_pool()
        if pool.remove_account(account_id):
            return {"ok": True, "message": f"Đã xóa tài khoản Flow: {account_id}"}
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Image Generation Endpoints ──────────────────────────────────────────────

@router.get("/image/config")
async def get_image_config():
    """Get current image generation configuration."""
    cfg_file = _get_hermes_dir() / "config.yaml"
    provider = "antigravity"
    aspect_ratio = "16:9"
    if cfg_file.is_file():
        try:
            import yaml
            with open(cfg_file, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
            img_cfg = d.get("image_gen", {})
            provider = img_cfg.get("provider", "antigravity")
            aspect_ratio = img_cfg.get("default_aspect_ratio", "16:9")
        except Exception:
            pass
    return {
        "ok": True,
        "provider": provider,
        "model": "gemini-3.1-flash-image",
        "aspect_ratio": aspect_ratio,
        "available_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
    }


@router.post("/image/config")
async def update_image_config(req: ImageConfigRequest):
    """Update image generation settings in config.yaml."""
    cfg_file = _get_hermes_dir() / "config.yaml"
    try:
        import yaml
        data = {}
        if cfg_file.is_file():
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        img = data.setdefault("image_gen", {})
        if req.aspect_ratio:
            img["default_aspect_ratio"] = req.aspect_ratio
        if req.provider:
            img["provider"] = req.provider
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False)
        return {"ok": True, "message": "Đã lưu cấu hình tạo ảnh thành công."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image/generate")
async def generate_image_test(req: ImageGenerateRequest):
    """Test image generation directly and return base64 preview."""
    try:
        try:
            from image_gen.antigravity import AntigravityImageGenProvider
        except ImportError:
            from plugins.image_gen.antigravity import AntigravityImageGenProvider

        provider = AntigravityImageGenProvider()
        res = provider.generate(req.prompt, aspect_ratio=req.aspect_ratio)

        if not res.get("success"):
            return {"ok": False, "error": res.get("error", "Generation failed")}

        img_path = res.get("image")
        b64_data = ""
        if img_path and os.path.isfile(img_path):
            with open(img_path, "rb") as f:
                b64_data = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"

        return {
            "ok": True,
            "image_path": img_path,
            "preview_data_url": b64_data,
            "model": res.get("model", "gemini-3.1-flash-image"),
            "aspect_ratio": req.aspect_ratio,
        }
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {"ok": False, "error": str(e)}


# ─── System Doctor Diagnostics & Logs ────────────────────────────────────────

@router.get("/doctor", response_model=DoctorReportResponse)
async def run_doctor_checks():
    """Run comprehensive self-diagnostics suite (6-Point Health Check)."""
    checks: List[DoctorCheckItem] = []
    hermes_dir = _get_hermes_dir()
    srv = _get_server_module()

    # 1. Antigravity OAuth Token Check
    try:
        auth_mgr = _get_ag_auth_manager()
        creds = auth_mgr.load_stored_credentials()
        if creds and not creds.is_expired:
            checks.append(DoctorCheckItem(
                id="oauth_token",
                label="Antigravity OAuth Token",
                status="ok",
                message=f"Hợp lệ ({creds.email or 'Primary User'})",
                detail=f"Project ID: {creds.project_id or 'auto-detected'}",
            ))
        elif creds and creds.refresh_token:
            checks.append(DoctorCheckItem(
                id="oauth_token",
                label="Antigravity OAuth Token",
                status="ok",
                message="Tự động gia hạn ngầm sẵn sàng",
                detail="Access token tạm hết hạn nhưng đã có refresh token.",
            ))
        else:
            checks.append(DoctorCheckItem(
                id="oauth_token",
                label="Antigravity OAuth Token",
                status="warn",
                message="Chưa đăng nhập",
                detail="Nhấn 'Đăng nhập Google OAuth' để xác thực tài khoản.",
            ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="oauth_token",
            label="Antigravity OAuth Token",
            status="error",
            message=f"Lỗi đọc token: {e}",
        ))

    # 2. Multi-Account Pool Check
    try:
        pool = _get_ag_account_pool()
        accs = pool.list_accounts()
        avail = sum(1 for a in accs if a.is_available)
        strat = pool.get_rotation_strategy()
        checks.append(DoctorCheckItem(
            id="account_pool",
            label="Multi-Account Pool",
            status="ok" if avail > 0 else "warn",
            message=f"{len(accs)} tài khoản ({avail} sẵn sàng)",
            detail=f"Chiến lược xoay vòng: {strat.upper()}",
        ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="account_pool",
            label="Multi-Account Pool",
            status="warn",
            message=f"Pool không khả dụng: {e}",
        ))

    # 3. Bridge Daemon Health Check
    try:
        running = srv.is_server_running(srv.DEFAULT_BRIDGE_HOST, srv.DEFAULT_BRIDGE_PORT)
        checks.append(DoctorCheckItem(
            id="bridge_daemon",
            label="Bridge Daemon (Port 8100)",
            status="ok" if running else "info",
            message="Đang hoạt động (ONLINE)" if running else "Ở chế độ chờ (STANDBY - Auto Wake)",
            detail="Tự động thức dậy khi Hermes gửi câu lệnh hoặc nhấn nút Start.",
        ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="bridge_daemon",
            label="Bridge Daemon",
            status="error",
            message=f"Lỗi kiểm tra server: {e}",
        ))

    # 4. Google Flow Session Check
    try:
        svc = _get_auth_service()
        st = svc.get_status()
        if st.get("connected"):
            checks.append(DoctorCheckItem(
                id="flow_session",
                label="Google Flow Veo 3.1 Session",
                status="ok",
                message=f"Đã kết nối ({st.get('email')}, {st.get('credits', 0)} credits)",
                detail="Session 30 ngày & tự động duy trì phiên ngầm đang bật.",
            ))
        else:
            checks.append(DoctorCheckItem(
                id="flow_session",
                label="Google Flow Veo 3.1 Session",
                status="warn",
                message="Chưa kết nối Google Flow",
                detail="Nhấn '1-Click Handshake' tại Tab Google Flow để kết nối.",
            ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="flow_session",
            label="Google Flow Session",
            status="warn",
            message=f"Lỗi kết nối Flow: {e}",
        ))

    # 5. Dynamic Models Discovery Check
    try:
        try:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
        except ImportError:
            from bridge.models import ModelDiscoveryManager
        dmgr = ModelDiscoveryManager()
        models = dmgr.get_discovered_models(force_refresh=False)
        checks.append(DoctorCheckItem(
            id="model_discovery",
            label="Danh mục 32+ Mô hình Dynamic",
            status="ok" if models else "warn",
            message=f"{len(models)} mô hình đã khám phá" if models else "Chưa đồng bộ mô hình",
            detail="Bao gồm Gemini 3.7 Pro/Flash, Claude Sonnet 4.6, Claude Opus 4.6, GPT-OSS 120B.",
        ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="model_discovery",
            label="Danh mục Mô hình",
            status="warn",
            message=f"Không thể khám phá mô hình: {e}",
        ))

    # 6. Hermes Config & Upgrade Persistence Check
    try:
        dest_plugin = hermes_dir / "plugins" / "model-providers" / "antigravity" / "injector.py"
        dest_bridge = hermes_dir / "bridge" / "antigravity" / "tools" / "antigravity_bridge"
        is_synced = dest_plugin.is_file() and dest_bridge.is_dir()
        checks.append(DoctorCheckItem(
            id="upgrade_persistence",
            label="Đồng bộ & Bền vững (~/.hermes/)",
            status="ok" if is_synced else "warn",
            message="Đã đồng bộ an toàn" if is_synced else "Cần đồng bộ qua install.py",
            detail="Đảm bảo plugin không bị mất khi Hermes cập nhật git core.",
        ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="upgrade_persistence",
            label="Upgrade Persistence",
            status="warn",
            message=f"Lỗi kiểm tra tệp: {e}",
        ))

    # 7. Dedicated Gemini Web App Pool Check
    try:
        gweb_pool = _get_gemini_web_pool()
        snap = gweb_pool.get_dashboard_pool_snapshot()
        r_nodes = snap.get("ready_nodes", 0)
        t_nodes = snap.get("total_nodes", 0)
        r_mode = snap.get("config", {}).get("routing_mode", "hybrid_failover")
        checks.append(DoctorCheckItem(
            id="gemini_web_pool",
            label="Gemini Web App Quota Pool",
            status="ok" if r_nodes > 0 else "info",
            message=f"{r_nodes}/{t_nodes} node sẵn sàng ({r_mode})" if t_nodes > 0 else "Chưa gắn node Web (Tùy chọn)",
            detail="Khai thác hạn mức Gemini Argon / 2.5 Pro / 2.5 Flash từ gemini.google.com/app.",
        ))
    except Exception as e:
        checks.append(DoctorCheckItem(
            id="gemini_web_pool",
            label="Gemini Web App Quota Pool",
            status="warn",
            message=f"Lỗi kiểm tra bể Gemini Web: {e}",
        ))

    # Compute overall score
    ok_count = sum(1 for c in checks if c.status in ("ok", "info"))
    score = int((ok_count / len(checks)) * 100) if checks else 0
    all_good = not any(c.status == "error" for c in checks)

    return DoctorReportResponse(all_good=all_good, score=score, checks=checks)


@router.get("/logs")
async def get_recent_logs(lines: int = Query(default=100, ge=10, le=500)):
    """Fetch the latest tail of antigravity_bridge.log."""
    srv = _get_server_module()
    log_file = srv.get_log_file()
    if not log_file.is_file():
        return {"ok": True, "lines": [], "log_file": str(log_file), "count": 0}

    try:
        max_bytes = 64 * 1024
        with open(log_file, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes), os.SEEK_SET)
            content = f.read().decode("utf-8", errors="replace")
        all_lines = content.splitlines()
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {
            "ok": True,
            "lines": tail,
            "total_lines": len(all_lines),
            "log_file": str(log_file),
            "count": len(tail),
        }
    except Exception as e:
        return {"ok": False, "lines": [], "error": str(e), "log_file": str(log_file), "count": 0}


# ─── Dedicated Gemini Web App Pool Management Endpoints ───────────────────────

def _get_gemini_web_pool():
    try:
        from tools.antigravity_bridge.gemini_web import GeminiWebPoolManager
    except ImportError:
        from bridge.gemini_web import GeminiWebPoolManager
    return GeminiWebPoolManager(hermes_dir=_get_hermes_dir())


def _get_gemini_web_client(pool=None):
    try:
        from tools.antigravity_bridge.gemini_web import GeminiWebClient
    except ImportError:
        from bridge.gemini_web import GeminiWebClient
    return GeminiWebClient(pool_manager=pool or _get_gemini_web_pool())


class GeminiWebConfigRequest(BaseModel):
    routing_mode: Optional[str] = None  # "hybrid_failover" | "web_first" | "isolated"
    rotation_strategy: Optional[str] = None  # "sticky_session" | "least_used" | "round_robin"
    auto_rotate_cookies: Optional[bool] = None
    preserve_server_context: Optional[bool] = None
    proactive_switch_remaining_pct: Optional[float] = None


class GeminiWebNodeImportRequest(BaseModel):
    raw_cookie_input: str = ""
    psid: str = ""
    psidts: str = ""
    email: str = ""
    display_name: str = ""
    node_id: str = ""
    linked_oauth_account_id: str = ""
    verify_immediately: bool = True


class GeminiWebNodeToggleRequest(BaseModel):
    node_id: str
    enabled: Optional[bool] = None


class GeminiWebNodeLimitsRequest(BaseModel):
    node_id: str
    argon_hourly_limit: Optional[int] = None
    argon_daily_limit: Optional[int] = None
    pro_hourly_limit: Optional[int] = None
    pro_daily_limit: Optional[int] = None
    flash_hourly_limit: Optional[int] = None
    flash_daily_limit: Optional[int] = None
    default_web_model: Optional[str] = None
    reset_usage: bool = False


class GeminiWebNodeRotateRequest(BaseModel):
    node_id: Optional[str] = None  # If None or empty, rotates all nodes in pool


class GeminiWebNodeTestRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    node_id: Optional[str] = None
    model: str = "gemini-web-argon"
    prompt: str = "Xin chào! Hãy xác nhận ngắn gọn bạn đang hoạt động qua Gemini Web App."


_GWEB_HANDSHAKE_SESSIONS: Dict[str, Dict[str, Any]] = {}


async def _auto_sync_gemini_web_pool(pool) -> List[Dict[str, Any]]:
    """Auto-discover and import/update nodes from local Browser profiles, Camofox, Flow, and Google OAuth Pool."""
    discovered = pool.session_manager.discover_cookies_from_local_browser_profiles(
        include_system_profiles=True
    )
    imported_nodes: List[Dict[str, Any]] = []
    for item in discovered:
        cookies = item.get("cookies") or {}
        res = await pool.import_or_update_node(
            psid=cookies.get("__Secure-1PSID", ""),
            psidts=cookies.get("__Secure-1PSIDTS", ""),
            raw_cookie_input="; ".join(f"{k}={v}" for k, v in cookies.items()),
            email=item.get("email") or "",
            display_name=item.get("display_name") or "",
            linked_oauth_account_id=item.get("linked_oauth_account_id") or "",
            verify_immediately=True,
        )
        if res.get("node"):
            imported_nodes.append(res["node"])
    return imported_nodes


@router.get("/gemini-web/pool")
async def get_gemini_web_pool():
    """Return full status, configuration, and sliding-window quota ledger of the Dedicated Gemini Web Pool."""
    try:
        pool = _get_gemini_web_pool()
        if not pool.list_nodes():
            try:
                await _auto_sync_gemini_web_pool(pool)
            except Exception as sync_err:
                logger.debug("Auto-bootstrap Gemini Web Pool skipped: %s", sync_err)
        return pool.get_dashboard_pool_snapshot()
    except Exception as e:
        logger.error("Failed to fetch Gemini Web Pool snapshot: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gemini-web/config")
async def update_gemini_web_config(req: GeminiWebConfigRequest):
    """Update global routing mode, rotation strategy, and context settings for the Gemini Web Pool."""
    try:
        pool = _get_gemini_web_pool()
        cfg = pool.update_config(
            routing_mode=req.routing_mode,
            rotation_strategy=req.rotation_strategy,
            auto_rotate_cookies=req.auto_rotate_cookies,
            preserve_server_context=req.preserve_server_context,
            proactive_switch_remaining_pct=req.proactive_switch_remaining_pct,
        )
        return {
            "ok": True,
            "message": f"Đã cập nhật cấu hình bể Gemini Web (Mode: {cfg.get('routing_mode')}, Strategy: {cfg.get('rotation_strategy')}).",
            "config": cfg,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gemini-web/nodes/import")
async def import_gemini_web_node(req: GeminiWebNodeImportRequest):
    """Import or update a Gemini Web App node from Cookie string, JSON Cookie-Editor, cURL, or 2 fields."""
    try:
        pool = _get_gemini_web_pool()
        res = await pool.import_or_update_node(
            raw_cookie_input=req.raw_cookie_input,
            psid=req.psid,
            psidts=req.psidts,
            email=req.email,
            display_name=req.display_name,
            node_id=req.node_id,
            linked_oauth_account_id=req.linked_oauth_account_id,
            verify_immediately=req.verify_immediately,
        )
        if not res.get("ok") and not res.get("node"):
            return {"ok": False, "error": res.get("error") or "Không thể nhập Cookie Gemini Web."}
        node_info = res.get("node") or {}
        hs = res.get("handshake") or {}
        msg = (
            f"Đã gắn thành công Gemini Web Node ({node_info.get('display_name')}) — Gói: {node_info.get('tier_badge')}"
            if hs.get("ok")
            else f"Đã lưu Cookie cho {node_info.get('display_name')} nhưng xác thực trực tuyến chưa hoàn tất: {hs.get('error', '')}"
        )
        return {
            "ok": bool(hs.get("ok", True)),
            "message": msg,
            "node": node_info,
            "handshake": hs,
        }
    except Exception as e:
        logger.error("Failed importing Gemini Web node: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/gemini-web/nodes/sync-browser")
async def sync_gemini_web_nodes_from_browser():
    """Auto-discover and import `.google.com` cookies & Google sessions from Browser/Camofox/Flow/OAuth Pool."""
    try:
        pool = _get_gemini_web_pool()
        imported_nodes = await _auto_sync_gemini_web_pool(pool)
        if not imported_nodes:
            return {
                "ok": False,
                "imported_count": 0,
                "message": "Chưa tìm thấy phiên Google nào trong Browser Profile hoặc OAuth Pool. Hãy bấm '+ Thêm Node Web (Tự Động)' để đăng nhập Google 1-Chạm!",
            }

        emails_str = ", ".join(
            n.get("email") or n.get("display_name") or n.get("node_id")
            for n in imported_nodes[:5]
        )
        return {
            "ok": True,
            "imported_count": len(imported_nodes),
            "nodes": imported_nodes,
            "pool": pool.get_dashboard_pool_snapshot(),
            "message": f"Đã tự động bắt & đồng bộ {len(imported_nodes)} Node Gemini Web ({emails_str})!",
        }
    except Exception as e:
        return {"ok": False, "imported_count": 0, "error": str(e)}


@router.post("/gemini-web/handshake/start")
async def start_gemini_web_auto_handshake():
    """1-Click Automatic Session Capture for Gemini Web App:
    1. Immediately scans & imports existing Browser / Camofox / Flow / Google OAuth sessions.
    2. If running on Desktop with GUI display and no nodes exist yet, launches Playwright to gemini.google.com/app.
    """
    try:
        pool = _get_gemini_web_pool()
        imported_nodes = await _auto_sync_gemini_web_pool(pool)
        session_id = f"gweb_hs_{int(time.time() * 1000)}"

        if imported_nodes:
            emails = [n.get("email") or n.get("display_name") for n in imported_nodes]
            _GWEB_HANDSHAKE_SESSIONS[session_id] = {
                "session_id": session_id,
                "status": "completed",
                "imported_count": len(imported_nodes),
                "emails": emails,
                "message": f"Đã tự động bắt thành công {len(imported_nodes)} phiên Google ({', '.join(emails[:4])})!",
            }
            return {
                "ok": True,
                "session_id": session_id,
                "status": "completed",
                "imported_count": len(imported_nodes),
                "nodes": imported_nodes,
                "pool": pool.get_dashboard_pool_snapshot(),
                "message": _GWEB_HANDSHAKE_SESSIONS[session_id]["message"],
            }

        # No existing local profiles found; return auth_url for 1-click Google OAuth login
        _load_pkce_sessions()
        _ensure_local_oauth_callback_listener()
        auth_mgr = _get_ag_auth_manager()
        pkce = auth_mgr.create_pkce_auth_session()
        _PKCE_SESSIONS[pkce["session_id"]] = pkce
        _save_pkce_sessions()
        return {
            "ok": True,
            "session_id": pkce["session_id"],
            "status": "oauth_ready",
            "auth_url": pkce["auth_url"],
            "redirect_uri": pkce["redirect_uri"],
            "message": "Mở liên kết đăng nhập Google để tự động gắn Node vào bể Gemini Web.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "message": f"Lỗi khởi tạo bắt tự động: {e}"}


@router.get("/gemini-web/handshake/poll/{session_id}")
async def poll_gemini_web_auto_handshake(session_id: str):
    """Poll status of an ongoing 1-Click Gemini Web Handshake."""
    info = _GWEB_HANDSHAKE_SESSIONS.get(session_id)
    if not info:
        pool = _get_gemini_web_pool()
        snap = pool.get_dashboard_pool_snapshot()
        return {
            "ok": True,
            "status": "completed" if snap.get("total_nodes", 0) > 0 else "pending",
            "pool": snap,
        }
    return {"ok": True, **info}



@router.post("/gemini-web/nodes/toggle")
async def toggle_gemini_web_node(req: GeminiWebNodeToggleRequest):
    """Enable or pause a specific Gemini Web node independently of Code Assist."""
    try:
        pool = _get_gemini_web_pool()
        node = pool.toggle_node(req.node_id, enabled=req.enabled)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node '{req.node_id}' not found.")
        state_str = "ĐANG BẬT (Active)" if node.enabled else "TẠM DỪNG (Paused)"
        return {
            "ok": True,
            "message": f"Node '{node.display_name}' đã chuyển sang trạng thái: {state_str}",
            "node": pool.format_node_for_dashboard(node),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gemini-web/nodes/limits")
async def update_gemini_web_node_limits(req: GeminiWebNodeLimitsRequest):
    """Update hourly/daily sliding-window quota limits, default model, or reset counters for a node."""
    try:
        pool = _get_gemini_web_pool()
        limits_update = {}
        for field_name in (
            "argon_hourly_limit",
            "argon_daily_limit",
            "pro_hourly_limit",
            "pro_daily_limit",
            "flash_hourly_limit",
            "flash_daily_limit",
        ):
            val = getattr(req, field_name, None)
            if val is not None:
                limits_update[field_name] = int(val)

        node = pool.update_node_limits(
            node_id=req.node_id,
            limits=limits_update if limits_update else None,
            default_web_model=req.default_web_model,
            reset_usage=req.reset_usage,
        )
        if not node:
            raise HTTPException(status_code=404, detail=f"Node '{req.node_id}' not found.")
        return {
            "ok": True,
            "message": f"Đã cập nhật trần hạn mức & bộ đếm cho node '{node.display_name}'.",
            "node": pool.format_node_for_dashboard(node),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gemini-web/nodes/rotate")
async def rotate_gemini_web_cookies(req: GeminiWebNodeRotateRequest):
    """Force rotate `__Secure-1PSIDTS` (`RotateCookies`) and refresh `SNlM0e` + models for one or all nodes."""
    try:
        pool = _get_gemini_web_pool()
        target_nodes = [pool.get_node(req.node_id)] if req.node_id else pool.list_nodes()
        target_nodes = [n for n in target_nodes if n is not None]
        if not target_nodes:
            return {"ok": False, "message": "Không tìm thấy node Gemini Web nào để xoay Cookie."}

        results = []
        for n in target_nodes:
            rot_ok, rot_msg = await pool.session_manager.rotate_1psidts(n.node_id)
            probe = await pool.session_manager.handshake_and_probe_models(n.node_id)
            if probe.get("ok"):
                n.status = "ready"
                if probe.get("detected_tier"):
                    n.detected_tier = probe["detected_tier"]
                if probe.get("available_models"):
                    n.available_models = probe["available_models"]
                if probe.get("email") and not n.email:
                    n.email = probe["email"]
                n.last_error = ""
            else:
                n.status = str(probe.get("status") or "expired")
                n.last_error = str(probe.get("error") or rot_msg)
            results.append(
                {
                    "node_id": n.node_id,
                    "rotate_ok": rot_ok,
                    "handshake_ok": bool(probe.get("ok")),
                    "message": rot_msg if probe.get("ok") else probe.get("error"),
                }
            )

        # Persist updated node statuses
        cfg = pool.get_config()
        pool._save_pool_raw(cfg, pool.list_nodes())
        ok_cnt = sum(1 for r in results if r["handshake_ok"] or r["rotate_ok"])
        return {
            "ok": ok_cnt > 0,
            "message": f"Đã xoay Cookie & kiểm tra phiên cho {ok_cnt}/{len(results)} node Gemini Web.",
            "results": results,
            "pool": pool.get_dashboard_pool_snapshot(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/gemini-web/nodes/test")
async def test_gemini_web_node_inference(req: GeminiWebNodeTestRequest):
    """Execute a live inference test against `gemini.google.com/app` on the selected node & model."""
    t0 = time.time()
    try:
        pool = _get_gemini_web_pool()
        client = _get_gemini_web_client(pool)
        payload = {
            "model": req.model or "gemini-web-argon",
            "messages": [{"role": "user", "content": req.prompt}],
        }
        completion = await client.create_chat_completion(
            payload,
            preferred_node_id=req.node_id or "",
        )
        latency_ms = int((time.time() - t0) * 1000)
        choice = (completion.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "node_id": completion.get("x_gemini_web_node"),
            "model": completion.get("x_gemini_web_model") or req.model,
            "reply": msg.get("content") or "",
            "reasoning": msg.get("reasoning_content") or "",
        }
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": str(e),
        }


@router.delete("/gemini-web/nodes/{node_id}")
async def delete_gemini_web_node(node_id: str):
    """Remove a node and its encrypted cookies from the Gemini Web Pool."""
    try:
        pool = _get_gemini_web_pool()
        if pool.remove_node(node_id):
            return {"ok": True, "message": f"Đã xóa node Gemini Web: {node_id}"}
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


