"""Antigravity & Google Flow Dashboard Plugin API.

Mounted at /api/plugins/antigravity/ by the Hermes Dashboard plugin system.
Provides endpoints for:
- Checking Google Flow status and remaining credits.
- 1-Click Handshake login initiation, polling, and cancellation.
- Headless Auto-Refresh triggering.
- Session disconnection.
- Model discovery status for Google Antigravity Code Assist.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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


# ─── Helper Functions ────────────────────────────────────────────────────────

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


# ─── Endpoints ────────────────────────────────────────────────────────────────

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


@router.get("/antigravity/models")
async def get_antigravity_models():
    """List models dynamically discovered from Antigravity IDE."""
    try:
        try:
            from bridge.models import ModelDiscoveryManager
        except ImportError:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
        mgr = ModelDiscoveryManager()
        models = mgr.get_available_models()
        return {"ok": True, "count": len(models), "models": models}
    except Exception as e:
        return {"ok": False, "count": 0, "models": [], "error": str(e)}
