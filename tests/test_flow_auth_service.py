"""Unit & Integration Tests for Google Flow 1-Click Handshake and Auto-Refresh Daemon."""

import asyncio
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from bridge.flow.flow_auth_service import FlowAuthService, HandshakeSession
from bridge.flow.flow_refresh_daemon import FlowRefreshDaemon


def test_flow_auth_service_status_connected():
    """Test get_status correctly parses valid token."""
    svc = FlowAuthService.get_instance()
    status = svc.get_status()

    assert isinstance(status, dict)
    assert "connected" in status
    assert "email" in status
    assert "is_expired" in status
    assert "expires_in_seconds" in status
    assert "has_session_cookie" in status


def test_flow_auth_service_save_session(tmp_path):
    """Test save_session_data creates valid JSON payload."""
    svc = FlowAuthService()
    test_token_file = tmp_path / "flow_token.json"

    with patch("bridge.flow.flow_auth_service.get_token_path", return_value=test_token_file):
        ok = svc.save_session_data(
            token="ya29.test_token_12345",
            email="testuser@gmail.com",
            raw_session={
                "user": {"name": "Test User", "email": "testuser@gmail.com"},
                "expires": "2026-09-04T12:00:00.000Z",
                "credits": 999
            }
        )
        assert ok is True
        assert test_token_file.is_file()

        saved = json.loads(test_token_file.read_text(encoding="utf-8"))
        assert saved["access_token"] == "ya29.test_token_12345"
        assert saved["email"] == "testuser@gmail.com"
        assert saved["user"]["name"] == "Test User"
        assert saved["credits"] == 999


def test_handshake_session_lifecycle():
    """Test handshake session registration, polling, and cancellation."""
    svc = FlowAuthService()
    session = HandshakeSession(
        session_id="test-session-xyz",
        expires_at=time.time() + 60,
    )
    svc._active_sessions[session.session_id] = session

    # Lookup
    found = svc.get_handshake_session("test-session-xyz")
    assert found is not None
    assert found.status == "pending"

    # Cancel
    cancelled = svc.cancel_handshake("test-session-xyz")
    assert cancelled is True
    assert found.status == "cancelled"
    assert found.cancel_requested is True


def test_flow_refresh_daemon_token_valid():
    """Test ensure_active_token returns current token if still valid."""
    async def _test():
        daemon = FlowRefreshDaemon.get_instance()

        with patch.object(FlowAuthService, "get_status", return_value={
            "connected": True,
            "is_expired": False,
            "expires_in_seconds": 3600,
        }), patch.object(FlowAuthService, "get_token_data", return_value={
            "access_token": "ya29.valid_token_mock",
        }):
            ok, tok = await daemon.ensure_active_token(min_validity_seconds=300)
            assert ok is True
            assert tok == "ya29.valid_token_mock"
    asyncio.run(_test())


def test_dashboard_plugin_api_routes():
    """Test dashboard plugin API routes using FastAPI TestClient."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/antigravity")
    client = TestClient(app)

    # 1. GET /flow/status
    res = client.get("/api/plugins/antigravity/flow/status")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "email" in data
    assert "is_expired" in data

    # 2. POST /flow/login-start
    with patch.object(FlowAuthService, "start_handshake") as mock_start:
        mock_start.return_value = HandshakeSession(
            session_id="mock-session-123",
            expires_at=time.time() + 180,
            status="pending"
        )
        res_login = client.post("/api/plugins/antigravity/flow/login-start?timeout=180")
        assert res_login.status_code == 200
        login_data = res_login.json()
        assert login_data["ok"] is True
        assert login_data["session_id"] == "mock-session-123"

    # 3. GET /flow/login-poll/mock-session-123
    with patch.object(FlowAuthService, "get_handshake_session") as mock_poll:
        mock_poll.return_value = HandshakeSession(
            session_id="mock-session-123",
            status="completed",
            email="testuser@gmail.com"
        )
        res_poll = client.get("/api/plugins/antigravity/flow/login-poll/mock-session-123")
        assert res_poll.status_code == 200
        poll_data = res_poll.json()
        assert poll_data["connected"] is True
        assert poll_data["email"] == "testuser@gmail.com"
