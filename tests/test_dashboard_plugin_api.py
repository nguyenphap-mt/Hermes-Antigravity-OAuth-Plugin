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
