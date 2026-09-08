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
        from bridge.auth import AntigravityAuthManager
        return AntigravityAuthManager()
    except ImportError:
        try:
            from tools.antigravity_bridge.auth import AntigravityAuthManager
            return AntigravityAuthManager()
        except ImportError:
            raise HTTPException(status_code=500, detail="AntigravityAuthManager could not be imported.")


def _get_ag_account_pool():
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
        return AntigravityAccountPoolManager()
    except ImportError:
        try:
            from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
            return AntigravityAccountPoolManager()
        except ImportError:
            raise HTTPException(status_code=500, detail="AntigravityAccountPoolManager could not be imported.")


def _get_server_module():
    try:
        import bridge.server as srv
        return srv
    except ImportError:
        try:
            import tools.antigravity_bridge.server as srv
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
            f"import sys; sys.path.insert(0, r'{_PLUGIN_ROOT}'); sys.path.insert(0, r'{_REPO_ROOT}'); "
            f"from bridge.server import run_server; run_server(host='{host}', port={port})",
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
        role = getattr(acc, "role", getattr(acc, "assigned_role", "all"))
        usage_count = getattr(acc, "request_count", getattr(acc, "total_requests", 0))
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
        ))

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
    acc = pool.get_account(email)
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account '{email}' not found.")
    acc.role = role
    pool._save_pool()
    return {"ok": True, "message": f"Đã gán vai trò '{role}' cho tài khoản {email}"}


@router.post("/accounts/login-start")
async def start_oauth_login():
    """Launch Google OAuth PKCE interactive login flow in background."""
    auth_mgr = _get_ag_auth_manager()
    loop = asyncio.get_event_loop()

    def _login_worker():
        return auth_mgr.login_interactive(open_browser=True)

    try:
        creds = await loop.run_in_executor(None, _login_worker)
        pool = _get_ag_account_pool()
        pool.add_or_update_account(creds)
        pool.set_active_account(creds.email)
        return {"ok": True, "email": creds.email, "message": "Đăng nhập Google OAuth thành công!"}
    except Exception as e:
        logger.error(f"OAuth login failed: {e}")
        return {"ok": False, "error": str(e), "message": f"Đăng nhập thất bại: {e}"}


# ─── Live Models Discovery & Quota Summary ───────────────────────────────────

@router.get("/antigravity/models")
async def get_antigravity_models(refresh: bool = False):
    """List models dynamically discovered from Antigravity IDE / Code Assist."""
    try:
        try:
            from bridge.models import ModelDiscoveryManager
        except ImportError:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
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
async def get_antigravity_quota(refresh: bool = False):
    """Fetch live quota buckets and rate limit summary from Code Assist API."""
    try:
        try:
            from bridge.models import ModelDiscoveryManager
        except ImportError:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
        mgr = ModelDiscoveryManager()
        summary = mgr.fetch_quota_summary(force_refresh=refresh)
        return {"ok": True, "summary": summary}
    except Exception as e:
        logger.error(f"Failed to fetch quota: {e}")
        return {"ok": False, "summary": {}, "error": str(e)}


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
    success, result = await daemon.ensure_active_token(min_validity_seconds=86400)
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
        from bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        try:
            from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager
        except ImportError:
            return {"ok": True, "accounts": [], "active_id": "default"}

    pool = FlowAccountPoolManager()
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
        from bridge.flow.account_pool import FlowAccountPoolManager
        pool = FlowAccountPoolManager()
        pool.set_active_account(account_id)
        return {"ok": True, "message": f"Đã đổi tài khoản Google Flow sang: {account_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flow/accounts/remove")
async def remove_flow_account(account_id: str = Query(...)):
    """Remove an account from Google Flow pool."""
    try:
        from bridge.flow.account_pool import FlowAccountPoolManager
        pool = FlowAccountPoolManager()
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
            from bridge.models import ModelDiscoveryManager
        except ImportError:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
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

    # Compute overall score
    ok_count = sum(1 for c in checks if c.status == "ok")
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
        content = log_file.read_text(encoding="utf-8", errors="replace")
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

