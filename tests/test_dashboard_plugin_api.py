import json
import os
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from dashboard.plugin_api import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/antigravity")
    return TestClient(app)


class TestDashboardPluginAPI:
    """Test suite for Antigravity & Google Flow Cockpit Dashboard."""

    def test_manifest_schema_and_fields(self):
        manifest_path = _PLUGIN_DIR / "dashboard" / "manifest.json"
        assert manifest_path.is_file(), "manifest.json must exist"

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["name"] == "antigravity"
        assert data["entry"] == "dist/index.js"
        assert data["css"] == "dist/style.css"
        assert data["api"] == "plugin_api.py"
        assert data["tab"]["path"] == "/antigravity"
        assert "settings:providers" in data.get("slots", [])

    def test_dist_bundle_files_exist(self):
        js_bundle = _PLUGIN_DIR / "dashboard" / "dist" / "index.js"
        css_file = _PLUGIN_DIR / "dashboard" / "dist" / "style.css"

        assert js_bundle.is_file(), "dist/index.js must exist"
        assert css_file.is_file(), "dist/style.css must exist"

        js_content = js_bundle.read_text(encoding="utf-8")
        assert "window.__HERMES_PLUGINS__.register(\"antigravity\"" in js_content
        assert "registerSlot(\"settings:providers\"" in js_content
        assert "AntigravityCockpit" in js_content
        assert "ag-badge-purple" in js_content
        assert "ag-quota-bar-wrap" in js_content
        assert "refresh-plan-quota" in js_content

        css_content = css_file.read_text(encoding="utf-8")
        assert ".ag-badge-purple" in css_content
        assert ".ag-badge-blue" in css_content
        assert ".ag-quota-bar-wrap" in css_content

    def test_daemon_status_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/daemon/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert data["port"] == 8100
        assert data["host"] == "127.0.0.1"
        assert "log_file" in data
        assert "pid_file" in data

    def test_accounts_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "accounts" in data
        assert "strategy" in data
        assert "mode" in data

    def test_antigravity_models_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/antigravity/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "models" in data
        assert "count" in data

    def test_flow_status_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/flow/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        assert "has_session_cookie" in data
        assert "status_label" in data

    def test_flow_accounts_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/flow/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "accounts" in data
        assert "active_id" in data

    def test_flow_models_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/flow/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["models"]) == 5
        model_ids = [m["id"] for m in data["models"]]
        assert "veo-3.1-lite-free" in model_ids
        assert "omni-1.1-flash" in model_ids
        assert "veo-3.1-quality" in model_ids

    def test_image_config_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/image/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["provider"] == "antigravity"
        assert data["model"] == "gemini-3.1-flash-image"
        assert "16:9" in data["available_aspect_ratios"]

    def test_doctor_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/doctor")
        assert resp.status_code == 200
        data = resp.json()
        assert "all_good" in data
        assert "score" in data
        assert len(data["checks"]) >= 6
        check_ids = [c["id"] for c in data["checks"]]
        assert "oauth_token" in check_ids
        assert "bridge_daemon" in check_ids
        assert "flow_session" in check_ids
        assert "model_discovery" in check_ids
        assert "upgrade_persistence" in check_ids

    def test_logs_endpoint(self, client):
        resp = client.get("/api/plugins/antigravity/logs?lines=20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "lines" in data
        assert "total_lines" in data

    def test_accounts_plan_quota_fields(self, client):
        resp = client.get("/api/plugins/antigravity/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        for acc in data["accounts"]:
            assert "plan_name" in acc
            assert "plan_type" in acc
            assert "quota_summary" in acc
            assert acc["plan_type"] in {"ultra", "pro", "free"}

    def test_refresh_plan_quota_endpoint(self, client):
        resp = client.post("/api/plugins/antigravity/accounts/refresh-plan-quota", json={"email": "nonexistent@example.com"})
        assert resp.status_code in {200, 400}

    def test_accounts_pro_tier_resolution(self, monkeypatch, client):
        """Verify accounts endpoint reports pro tier and Google AI Pro name when tier_id is g1-pro-tier."""
        from unittest.mock import MagicMock
        from dashboard import plugin_api

        mock_acc = MagicMock()
        mock_acc.email = "pro_user@gmail.com"
        mock_acc.tier_id = "g1-pro-tier"
        mock_acc.plan_name = ""
        mock_acc.plan_type = "free"
        mock_acc.computed_plan_type = "pro"
        mock_acc.display_plan_name = "Google AI Pro"
        mock_acc.quota_summary = {"gemini_weekly_pct": 85}
        mock_acc.status = "active"
        mock_acc.project_id = "aicode-consumers"
        mock_acc.expires_at = 0.0
        mock_acc.is_expired = False
        mock_acc.is_available = True
        mock_acc.exhausted_until = None
        mock_acc.role = "all"
        mock_acc.assigned_role = "all"
        mock_acc.total_requests = 10

        mock_pool = MagicMock()
        mock_pool.list_accounts.return_value = [mock_acc]
        mock_pool.get_active_account.return_value = mock_acc
        mock_pool.get_rotation_strategy.return_value = "sharded"

        monkeypatch.setattr(plugin_api, "_get_ag_account_pool", lambda: mock_pool)

        resp = client.get("/api/plugins/antigravity/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["accounts"]) == 1
        item = data["accounts"][0]
        assert item["email"] == "pro_user@gmail.com"
        assert item["plan_type"] == "pro"
        assert item["plan_name"] == "Google AI Pro"
        assert item["tier_id"] == "g1-pro-tier"

    def test_bilingual_vi_en_language_switcher(self):
        """Verify dashboard bundle includes full Vietnamese and English i18n switcher and dictionary."""
        js_bundle = _PLUGIN_DIR / "dashboard" / "dist" / "index.js"
        css_file = _PLUGIN_DIR / "dashboard" / "dist" / "style.css"

        js_content = js_bundle.read_text(encoding="utf-8")
        css_content = css_file.read_text(encoding="utf-8")

        assert 'LANG_STORAGE_KEY = "ag_cockpit_lang"' in js_content
        assert "function setCockpitLang" in js_content
        assert "function useCockpitLang" in js_content
        assert "function renderLanguageSwitcher" in js_content
        assert "VI_TO_EN_EXACT" in js_content
        assert "EN_TO_VI_EXACT" in js_content
        assert "VI_TO_EN_PATTERNS" in js_content
        assert "translateText" in js_content
        assert ".ag-lang-switch" in css_content
        assert ".ag-lang-btn-active" in css_content

    def test_gemini_web_ui_strict_web_session_and_no_oauth_pkce_leak(self):
        """Verify Gemini Web tab enforces authentic gemini.google.com cookies and removes OAuth PKCE localhost:51121 form."""
        js_bundle = _PLUGIN_DIR / "dashboard" / "dist" / "index.js"
        js_content = js_bundle.read_text(encoding="utf-8")

        assert "ag_pending_gweb_oauth" not in js_content
        assert "submitWebOAuthDirect" not in js_content
        assert "is_authentic_web_session" in js_content
        assert "CHỜ ĐĂNG NHẬP WEB" in js_content
        assert "Đặt lại lúc " in js_content

    def test_gemini_web_interactive_browser_login_endpoints_and_ui(self, monkeypatch, client):
        """Verify In-Dashboard Interactive Cloud Browser Login API routes and UI viewport integration."""
        from dashboard import plugin_api

        class _MockBrowserLoginMgr:
            async def start_session(self, email="", node_id="", pool=None):
                return {
                    "ok": True,
                    "session_id": "gweb_bl_test_123",
                    "status": "awaiting_login",
                    "width": 1024,
                    "height": 680,
                    "current_url": "https://accounts.google.com/v3/signin/challenge/pwd",
                    "image_b64": "ZmFrZV9qcGVn",
                    "completed": False,
                }

            async def get_state(self, session_id: str, pool=None):
                return {
                    "ok": True,
                    "session_id": session_id,
                    "status": "awaiting_login",
                    "width": 1024,
                    "height": 680,
                    "current_url": "https://accounts.google.com/v3/signin/challenge/pwd",
                    "image_b64": "ZmFrZV9qcGVn",
                    "completed": False,
                }

            async def send_action(self, **kwargs):
                return {
                    "ok": True,
                    "session_id": kwargs.get("session_id"),
                    "status": "completed",
                    "completed": True,
                    "message": "Đã đăng nhập thành công Gemini Web!",
                    "node": {"node_id": "gweb_lecao043_gmail_com", "email": "lecao043@gmail.com", "status": "ready"},
                }

            async def stop_session(self, session_id: str):
                return {"ok": True, "session_id": session_id, "stopped": True}

        monkeypatch.setattr(plugin_api, "_get_gemini_web_browser_login_manager", lambda: _MockBrowserLoginMgr())

        r_start = client.post(
            "/api/plugins/antigravity/gemini-web/browser-login/start",
            json={"email": "lecao043@gmail.com", "node_id": "gweb_lecao043_gmail_com"},
        )
        assert r_start.status_code == 200
        d_start = r_start.json()
        assert d_start["ok"] is True
        assert d_start["session_id"] == "gweb_bl_test_123"
        assert d_start["image_b64"] == "ZmFrZV9qcGVn"

        r_state = client.get("/api/plugins/antigravity/gemini-web/browser-login/state/gweb_bl_test_123")
        assert r_state.status_code == 200
        assert r_state.json()["ok"] is True

        r_input = client.post(
            "/api/plugins/antigravity/gemini-web/browser-login/input",
            json={"session_id": "gweb_bl_test_123", "action_type": "submit_text", "text": "secret"},
        )
        assert r_input.status_code == 200
        assert r_input.json()["completed"] is True

        r_stop = client.post(
            "/api/plugins/antigravity/gemini-web/browser-login/stop",
            json={"session_id": "gweb_bl_test_123"},
        )
        assert r_stop.status_code == 200
        assert r_stop.json()["stopped"] is True

        js_bundle = _PLUGIN_DIR / "dashboard" / "dist" / "index.js"
        js_content = js_bundle.read_text(encoding="utf-8")
        assert "/gemini-web/browser-login/start" in js_content
        assert "/gemini-web/browser-login/state/" in js_content
        assert "/gemini-web/browser-login/input" in js_content
        assert "/gemini-web/browser-login/stop" in js_content
        assert "ag-modal-dialog-wide" in js_content





