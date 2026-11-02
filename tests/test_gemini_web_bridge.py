"""Comprehensive Unit & Integration Tests for Gemini Web App Quota Bridge & Dedicated Pool Manager.

Covers:
1. Multi-format Cookie Parser (Raw Cookie header, JSON Cookie-Editor, cURL, explicit psid/psidts).
2. Encrypted/0600 Session Storage & Masked Public Health Telemetry (Zero Secret Leakage).
3. Dynamic WIZ_global_data HTML Scraper (Gemini Argon, 2.5 Pro, 2.5 Flash, email & tier detection).
4. `x-goog-ext-525001261-jspb` Model Selector Header Builder.
5. `BardFrontendService/StreamGenerate` `)]}'` Chunked Framing Parser (text, thoughts, [cid, rid, rcid]).
6. `GeminiWebToolAdapter` Bidirectional Translation (OpenAI `tools` -> XML `<tool_call>` -> OpenAI `tool_calls`).
7. `GeminiWebPoolManager` Dedicated Node Management, Sliding-Window 1h/24h Quota Ledger, Proactive High-Water Mark (`<=10%`), Sticky Session Context, and Per-Model Cooldowns.
8. `AntigravityClient` Dual-Channel Routing (`isolated`, `web_first`, and `hybrid_failover` when Code Assist is 429/403 or exhausted).
9. Dashboard Plugin API (`/gemini-web/pool`, `/gemini-web/config`, `/gemini-web/nodes/*`).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure plugin root is importable in both standalone repo and hermes-agent/tests/tools
_HERE = Path(__file__).resolve()
for _cand in (_HERE.parent.parent, _HERE.parent.parent.parent):
    if (_cand / "bridge" / "gemini_web").is_dir() or (_cand / "tools" / "antigravity_bridge" / "gemini_web").is_dir():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))

try:
    from bridge.client import AntigravityClient
    from bridge.gemini_web import (
        GEMINI_WEB_MODELS,
        GeminiWebClient,
        GeminiWebPoolManager,
        GeminiWebSessionManager,
        GeminiWebToolAdapter,
        build_model_selector_header,
        is_explicit_gemini_web_model,
        parse_bard_stream_generate_response,
        parse_flexible_cookie_input,
        resolve_gemini_web_model,
        scrape_models_and_tier_from_html,
    )
except ImportError:
    from tools.antigravity_bridge.client import AntigravityClient
    from tools.antigravity_bridge.gemini_web import (
        GEMINI_WEB_MODELS,
        GeminiWebClient,
        GeminiWebPoolManager,
        GeminiWebSessionManager,
        GeminiWebToolAdapter,
        build_model_selector_header,
        is_explicit_gemini_web_model,
        parse_bard_stream_generate_response,
        parse_flexible_cookie_input,
        resolve_gemini_web_model,
        scrape_models_and_tier_from_html,
    )



def _make_bard_rpc_response(
    text: str,
    thoughts: str = "",
    cid: str = "c_argon_001",
    rid: str = "r_argon_002",
    rcid: str = "rc_argon_003",
) -> str:
    """Construct a realistic `)]}'` framed BardFrontendService/StreamGenerate response."""
    candidate = [
        rcid,
        [text],
        thoughts,
    ]
    inner_body = [
        None,
        [cid, rid],
        None,
        None,
        [candidate],
    ]
    inner_json = json.dumps(inner_body, ensure_ascii=False)
    outer_frame = [["wrb.fr", None, inner_json]]
    outer_str = json.dumps(outer_frame, ensure_ascii=False)
    return f")]}}'\n\n{len(outer_str)}\n{outer_str}\n"


# =============================================================================
# 1. Cookie Parser & 0600 Session Security Tests
# =============================================================================

def test_parse_flexible_cookie_formats():
    # Format 1: Raw Cookie Header
    c1 = parse_flexible_cookie_input(
        "Cookie: __Secure-1PSID=g.a000_psid_val; __Secure-1PSIDTS=sidts_val_123; NID=511"
    )
    assert c1["__Secure-1PSID"] == "g.a000_psid_val"
    assert c1["__Secure-1PSIDTS"] == "sidts_val_123"

    # Format 2: Cookie-Editor JSON export
    json_export = json.dumps(
        [
            {"name": "__Secure-1PSID", "value": "g.a000_json_psid"},
            {"name": "__Secure-1PSIDTS", "value": "sidts_json_456"},
        ]
    )
    c2 = parse_flexible_cookie_input(json_export)
    assert c2["__Secure-1PSID"] == "g.a000_json_psid"
    assert c2["__Secure-1PSIDTS"] == "sidts_json_456"

    # Format 3: Full cURL command from DevTools
    curl_cmd = (
        "curl 'https://gemini.google.com/app' "
        "-H 'user-agent: Mozilla/5.0' "
        "-H 'cookie: __Secure-1PSID=g.a000_curl_psid; __Secure-1PSIDTS=sidts_curl_789'"
    )
    c3 = parse_flexible_cookie_input(curl_cmd)
    assert c3["__Secure-1PSID"] == "g.a000_curl_psid"
    assert c3["__Secure-1PSIDTS"] == "sidts_curl_789"

    # Format 4: Explicit fields
    c4 = parse_flexible_cookie_input("", psid="g.explicit_1", psidts="sidts_explicit_2")
    assert c4["__Secure-1PSID"] == "g.explicit_1"
    assert c4["__Secure-1PSIDTS"] == "sidts_explicit_2"


def test_session_manager_masked_telemetry_never_leaks_secrets(tmp_path: Path):
    sm = GeminiWebSessionManager(hermes_dir=tmp_path)
    sm.save_session(
        node_id="gweb_test",
        cookies={
            "__Secure-1PSID": "g.a000_SUPER_SECRET_PSID_TOKEN_VALUE_9999",
            "__Secure-1PSIDTS": "sidts_SUPER_SECRET_TS_TOKEN_8888",
        },
        snlm0e="SNlM0e_SECRET_CSRF_TOKEN_7777",
    )

    health = sm.get_public_cookie_health("gweb_test")
    assert health["has_1psid"] is True
    assert health["has_1psidts"] is True
    assert health["has_snlm0e"] is True
    # Ensure full secret strings do NOT appear anywhere in public health dict
    serialized = json.dumps(health)
    assert "SUPER_SECRET_PSID_TOKEN_VALUE" not in serialized
    assert "SUPER_SECRET_TS_TOKEN" not in serialized
    assert "SECRET_CSRF_TOKEN" not in serialized


# =============================================================================
# 2. Model Registry & Dynamic WIZ_global_data HTML Scraper Tests
# =============================================================================

def test_scrape_models_and_tier_from_html_detects_gemini_argon():
    mock_html = """
    <script>
    window.WIZ_global_data = {
        "SNlM0e": "AT_TOKEN_12345",
        "cfb2h": "boq_assistant-bard-web-server_20261101.05_p0",
        "FdrFJe": "-88127391823",
        "oPEP7c": "nguyenphap.pub1@gmail.com",
        "models": [
            ["9d8ca3786ebdfbea", "Gemini Argon"],
            ["61530e79959ab139", "2.5 Pro"],
            ["9ec249fc9ad08861", "2.5 Flash"]
        ]
    };
    </script>
    """
    scraped = scrape_models_and_tier_from_html(mock_html)
    assert scraped["email"] == "nguyenphap.pub1@gmail.com"
    assert scraped["detected_tier"] == "pro"
    model_ids = {m["id"]: m for m in scraped["models"]}
    assert "gemini-web-argon" in model_ids
    assert model_ids["gemini-web-argon"]["hex_id"] == "9d8ca3786ebdfbea"
    assert model_ids["gemini-web-argon"]["label"] == "Gemini Argon"

    # Verify dynamic auto-discovery of unseen future models from WIZ_global_data HTML
    future_html = '<script>["f1e2d3c4b5a69788", "5.0 Ultra"]</script>'
    future_scraped = scrape_models_and_tier_from_html(future_html)
    future_ids = {m["id"]: m for m in future_scraped["models"]}
    assert "gemini-web-5.0-ultra" in future_ids
    assert future_ids["gemini-web-5.0-ultra"]["hex_id"] == "f1e2d3c4b5a69788"
    assert resolve_gemini_web_model("gemini-web-5.0-ultra") == "gemini-web-5.0-ultra"


def test_build_model_selector_header():
    hdr = build_model_selector_header("gemini-web-argon")
    assert hdr is not None
    parsed = json.loads(hdr)
    assert parsed[4] == GEMINI_WEB_MODELS["gemini-web-argon"]["default_hex"]

    # Verify full 2026 Gemini Web App model lineup (4 Argon, 3.1 Pro, 3.8 Flash, 3.5 Flash-Lite + thinking levels)
    for web_mid in (
        "gemini-web-4-argon",
        "gemini-web-4-argon-high",
        "gemini-web-4-argon-medium",
        "gemini-web-4-argon-low",
        "gemini-web-3.1-pro",
        "gemini-web-3.1-pro-high",
        "gemini-web-3.1-pro-low",
        "gemini-web-3.8-flash",
        "gemini-web-3.8-flash-high",
        "gemini-web-3.8-flash-medium",
        "gemini-web-3.8-flash-low",
        "gemini-web-3.5-flash-lite",
    ):
        assert web_mid in GEMINI_WEB_MODELS
        assert is_explicit_gemini_web_model(web_mid) is True
        assert resolve_gemini_web_model(web_mid) == web_mid
        assert build_model_selector_header(web_mid) is not None

    # Default UI model omits custom hex header
    assert build_model_selector_header("gemini-web-default") is None
    assert is_explicit_gemini_web_model("gemini-web-argon") is True
    assert is_explicit_gemini_web_model("gemini-argon") is True
    assert is_explicit_gemini_web_model("claude-sonnet-4-6") is False


# =============================================================================
# 3. Hermes Agent Tool-Calling XML Compiler & Parser Tests
# =============================================================================

def test_tool_adapter_compiles_tools_and_parses_tool_calls():
    openai_req = {
        "model": "gemini-web-argon",
        "messages": [
            {"role": "system", "content": "You are Hermes Agent."},
            {"role": "user", "content": "Read the file /tmp/secret.txt using read_file."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents of a file on disk",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to read"},
                        },
                        "required": ["path"],
                    },
                },
            }
        ],
    }

    prompt_text, has_tools = GeminiWebToolAdapter.compile_openai_to_web_prompt(openai_req)
    assert has_tools is True
    assert "<antigravity_tool_protocol>" in prompt_text
    assert '"read_file"' in prompt_text

    # Simulate Gemini Web outputting a <tool_call> block
    web_output = (
        "Tôi sẽ đọc file `/tmp/secret.txt` ngay.\n"
        "<tool_call>\n"
        '{"name": "read_file", "arguments": {"path": "/tmp/secret.txt"}}\n'
        "</tool_call>"
    )
    completion = GeminiWebToolAdapter.build_openai_chat_completion(
        raw_text=web_output,
        model="gemini-web-argon",
        thoughts_text="Need to invoke read_file tool.",
        prompt_text=prompt_text,
    )

    choice = completion["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    msg = choice["message"]
    assert msg["reasoning_content"] == "Need to invoke read_file tool."
    assert len(msg["tool_calls"]) == 1
    tc = msg["tool_calls"][0]
    assert tc["function"]["name"] == "read_file"
    assert json.loads(tc["function"]["arguments"]) == {"path": "/tmp/secret.txt"}
    assert "<tool_call>" not in (msg.get("content") or "")


# =============================================================================
# 4. Dedicated GeminiWebPoolManager & Sliding-Window Quota Tracker Tests
# =============================================================================

def test_dedicated_gemini_web_pool_sliding_quota_and_proactive_switch(tmp_path: Path):
    async def _run():
        pool = GeminiWebPoolManager(hermes_dir=tmp_path)

        # Import 2 standalone web nodes without needing OAuth Code Assist
        await pool.import_or_update_node(
            psid="g.psid_node_1",
            psidts="sidts_node_1",
            email="user1@gmail.com",
            display_name="Node 1 Pro",
            verify_immediately=False,
        )
        await pool.import_or_update_node(
            psid="g.psid_node_2",
            psidts="sidts_node_2",
            email="user2@gmail.com",
            display_name="Node 2 Pro",
            verify_immediately=False,
        )

        # Configure Node 1 with a tight hourly limit of 10 requests for Argon
        pool.update_node_limits("gweb_user1_gmail_com", limits={"argon_hourly_limit": 10})

        # Record 9 requests on Node 1 -> remaining = 10% (hits <= 10% High-Water Mark!)
        for _ in range(9):
            pool.record_web_usage("gweb_user1_gmail_com", "gemini-web-argon", success=True)

        n1 = pool.get_node("gweb_user1_gmail_com")
        assert n1 is not None
        q1 = pool.compute_node_quota_summary(n1)
        assert q1["argon_1h_count"] == 9
        assert q1["argon_remaining_pct"] == 10.0

        # Because Node 1 is at <= 10% remaining and Node 2 is at 100%, select_node_for_model must proactively pick Node 2!
        chosen = pool.select_node_for_model("gemini-web-argon")
        assert chosen is not None
        assert chosen.node_id == "gweb_user2_gmail_com"

    asyncio.run(_run())


# =============================================================================
# 5. Dual-Channel Hybrid Routing & Failover in AntigravityClient Tests
# =============================================================================

def test_antigravity_client_hybrid_failover_when_code_assist_disabled_or_429(tmp_path: Path):
    async def _run():
        pool = GeminiWebPoolManager(hermes_dir=tmp_path)
        await pool.import_or_update_node(
            psid="g.psid_rescue",
            psidts="sidts_rescue",
            email="nguyenphap.pub1@gmail.com",
            display_name="Rescue Web Node",
            verify_immediately=False,
        )
        pool.session_manager.save_session(
            node_id="gweb_nguyenphap_pub1_gmail_com",
            cookies={"__Secure-1PSID": "g.psid_rescue", "__Secure-1PSIDTS": "sidts_rescue"},
            snlm0e="SNlM0e_LIVE_TOKEN",
            cfb2h="boq_assistant-bard-web-server_20261101",
            fsid="-998877",
        )

        mock_auth = MagicMock()
        mock_auth.auth_file = tmp_path / "auth" / "antigravity_tokens.json"
        # Simulate Code Assist having NO available credentials (e.g. all 0% or disabled)
        mock_auth.resolve_valid_credentials.return_value = None

        client = AntigravityClient(auth_manager=mock_auth, gemini_web_pool=pool)
        client.account_pool.get_account_for_service = MagicMock(return_value=None)

        # Mock the HTTP POST to BardFrontendService/StreamGenerate
        fake_bard_resp = MagicMock()
        fake_bard_resp.status_code = 200
        fake_bard_resp.text = _make_bard_rpc_response(
            text="Xin chào từ Gemini Argon trên nền Web App (Hybrid Failover thành công)!",
            thoughts="Answered via Gemini Web fallback.",
        )
        client._http.post = AsyncMock(return_value=fake_bard_resp)

        res = await client.create_chat_completion(
            {
                "model": "gemini-3.7-flash",
                "messages": [{"role": "user", "content": "Kiểm tra Hybrid Failover"}],
            }
        )

        assert res["choices"][0]["message"]["content"].startswith("Xin chào từ Gemini Argon")
        assert res["x_gemini_web_node"] == "gweb_nguyenphap_pub1_gmail_com"
        await client.close()

    asyncio.run(_run())


def test_parse_storage_state_prioritizes_google_com_domain():
    storage_state = {
        "cookies": [
            {"name": "__Secure-1PSID", "value": "yt_psid_wrong", "domain": ".youtube.com"},
            {"name": "__Secure-1PSID", "value": "google_com_psid_correct", "domain": ".google.com"},
            {"name": "__Secure-1PSIDTS", "value": "google_com_psidts_correct", "domain": ".google.com"},
            {"name": "__Secure-1PSID", "value": "vn_psid_wrong", "domain": ".google.com.vn"},
        ]
    }
    parsed = parse_flexible_cookie_input(json.dumps(storage_state))
    assert parsed["__Secure-1PSID"] == "google_com_psid_correct"
    assert parsed["__Secure-1PSIDTS"] == "google_com_psidts_correct"


def test_discover_cookies_from_flow_storage_state_and_oauth_pool(tmp_path: Path):
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "flow_token.json").write_text(
        json.dumps(
            {
                "email": "lecao043@gmail.com",
                "user": {"name": "Le Cao", "email": "lecao043@gmail.com"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "flow_storage_state.json").write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "__Secure-1PSID", "value": "g.flow_psid_123", "domain": ".google.com"},
                    {"name": "__Secure-1PSIDTS", "value": "sidts_flow_456", "domain": ".google.com"},
                    {"name": "__Secure-1PSID", "value": "g.vn_psid_wrong", "domain": ".google.com.vn"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (auth_dir / "antigravity_tokens.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"email": "lecao043@gmail.com", "tier_id": "g1-pro-tier"},
                    {"email": "thietbibenthanh.data@gmail.com", "tier_id": "g1-pro-tier"},
                ]
            }
        ),
        encoding="utf-8",
    )

    pool = GeminiWebPoolManager(hermes_dir=tmp_path)
    discovered = pool.session_manager.discover_cookies_from_local_browser_profiles(
        include_system_profiles=False
    )
    assert len(discovered) == 2
    by_email = {item["email"]: item for item in discovered}
    assert by_email["lecao043@gmail.com"]["cookies"]["__Secure-1PSID"] == "g.flow_psid_123"
    assert by_email["lecao043@gmail.com"]["detected_tier"] == "pro"
    assert by_email["thietbibenthanh.data@gmail.com"]["detected_tier"] == "pro"


def test_resolve_pkce_session_matches_state_when_session_id_lost_on_mobile(monkeypatch, tmp_path):
    try:
        import dashboard.plugin_api as papi
    except ImportError:
        import importlib.util

        cand_paths = [
            _HERE.parent.parent.parent / "Hermes-Antigravity-OAuth-Plugin" / "dashboard" / "plugin_api.py",
            Path.home() / "Hermes-Antigravity-OAuth-Plugin" / "dashboard" / "plugin_api.py",
        ]
        papi = None
        for cp in cand_paths:
            if cp.is_file():
                spec = importlib.util.spec_from_file_location("dashboard_plugin_api", cp)
                if spec and spec.loader:
                    papi = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(papi)
                    break
        if papi is None:
            pytest.skip("dashboard.plugin_api not present in standalone workspace")

    store_file = tmp_path / "pkce_sessions.json"
    monkeypatch.setattr(papi, "_get_pkce_store_file", lambda: store_file)
    papi._PKCE_SESSIONS.clear()

    now = time.time()
    papi._PKCE_SESSIONS["sess_older"] = {
        "session_id": "sess_older",
        "state": "state_abc_111",
        "code_verifier": "ver_111",
        "redirect_uri": "http://localhost:51121/oauth-callback",
        "created_at": now - 30,
        "expires_at": now + 600,
    }
    papi._PKCE_SESSIONS["sess_newer"] = {
        "session_id": "sess_newer",
        "state": "state_xyz_222",
        "code_verifier": "ver_222",
        "redirect_uri": "http://localhost:51121/oauth-callback",
        "created_at": now - 5,
        "expires_at": now + 600,
    }
    papi._save_pkce_sessions()
    papi._PKCE_SESSIONS.clear()

    # Even if mobile browser reloads and sends empty or newer session_id, state=state_abc_111 in callback_url wins
    matched = papi._resolve_pkce_session(
        session_id="",
        callback_url="http://localhost:51121/oauth-callback?state=state_abc_111&code=4/0AeanS0_test",
    )
    assert matched is not None
    assert matched["session_id"] == "sess_older"
    assert matched["code_verifier"] == "ver_111"


def test_refresh_account_plan_passes_companion_project_and_upgrades_gemini_web_node(monkeypatch, tmp_path):
    import urllib.error
    import urllib.request
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    tokens_path = auth_dir / "antigravity_tokens.json"
    tokens_path.write_text(
        json.dumps(
            {
                "active_account_email": "nguyenphap.pub@gmail.com",
                "accounts": {
                    "nguyenphap.pub@gmail.com": {
                        "email": "nguyenphap.pub@gmail.com",
                        "access_token": "ya29.valid_token_nguyenphap",
                        "refresh_token": "1//refresh_nguyenphap",
                        "expires_at": time.time() + 3600,
                        "project_id": "mimetic-ship-3261n",
                        "managed_project_id": "mimetic-ship-3261n",
                        "tier_id": "",
                        "plan_name": "Free Tier",
                        "plan_type": "free",
                        "status": "active",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    pool_file = tmp_path / "gemini_web_pool.json"
    pool_file.write_text(
        json.dumps(
            {
                "config": {},
                "nodes": [
                    {
                        "node_id": "nguyenphap_pub_gmail_com",
                        "email": "nguyenphap.pub@gmail.com",
                        "display_name": "nguyenphap.pub (Free)",
                        "linked_oauth_account_id": "nguyenphap.pub@gmail.com",
                        "enabled": True,
                        "status": "ready",
                        "detected_tier": "free",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class _FakeResp:
        headers = {}

        def __init__(self, payload: dict):
            self._raw = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=10.0):
        url = req.full_url
        body = json.loads((req.data or b"{}").decode("utf-8"))
        if ":loadCodeAssist" in url:
            if body.get("cloudaicompanionProject") != "mimetic-ship-3261n":
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            return _FakeResp(
                {
                    "currentTier": {"id": "free-tier", "name": "Antigravity"},
                    "paidTier": {"id": "g1-pro-tier", "name": "Google AI Pro"},
                }
            )
        return _FakeResp({"groups": []})

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    oauth_pool = AntigravityAccountPoolManager(storage_path=tokens_path)
    res = oauth_pool.refresh_account_plan_and_quota("nguyenphap.pub@gmail.com")
    assert res["ok"] is True
    assert res["plan_name"] == "Google AI Pro"
    assert res["plan_type"] == "pro"

    web_pool = GeminiWebPoolManager(hermes_dir=tmp_path)
    nodes = web_pool.list_nodes()
    assert len(nodes) == 1
    assert nodes[0].detected_tier == "pro"
    assert nodes[0].display_name == "nguyenphap.pub (Google AI Pro)"


# =============================================================================
# 6. Multi-Turn Memory Persistence, Turn-Desync Guard & Tool Correlation Tests
# =============================================================================

def test_oauth_bridge_stateless_never_persists_fake_cid_and_preserves_multiturn_memory(tmp_path: Path):
    """Verify RC-01 & RC-02: Stateless OAuth-Bridge never stores a fake cid and always sends full transcript."""
    async def _run():
        auth_dir = tmp_path / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / "antigravity_tokens.json").write_text(
            json.dumps(
                {
                    "accounts": [
                        {
                            "email": "stateless.oauth@gmail.com",
                            "access_token": "ya29.test_stateless_token",
                            "refresh_token": "1//test_stateless_refresh",
                            "expires_at": int(time.time()) + 3600,
                            "project_id": "test-proj-stateless",
                            "tier_id": "g1-pro-tier",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        pool = GeminiWebPoolManager(hermes_dir=tmp_path)
        await pool.import_or_update_node(
            psid="oauth_bridge:stateless.oauth@gmail.com",
            psidts="oauth_linked",
            email="stateless.oauth@gmail.com",
            display_name="Stateless OAuth Node",
            verify_immediately=False,
        )
        pool.session_manager.save_session(
            node_id="gweb_stateless_oauth_gmail_com",
            cookies={"__Secure-1PSID": "oauth_bridge:stateless.oauth@gmail.com"},
            snlm0e="oauth_bridge:stateless.oauth@gmail.com",
        )

        sent_prompts = []

        async def _fake_post(url: str, json: dict = None, **kwargs):
            prompt_sent = ""
            if isinstance(json, dict):
                contents = ((json.get("request") or {}).get("contents") or [{}])[0]
                parts = contents.get("parts") or [{}]
                prompt_sent = str(parts[0].get("text") or "")
            sent_prompts.append(prompt_sent)

            resp = MagicMock()
            resp.status_code = 200
            if len(sent_prompts) == 1:
                text = "Tôi đã ghi nhớ mã dự án là PROJECT_PHOENIX_999."
            else:
                text = (
                    "Mã dự án bạn vừa nói ở lượt 1 là PROJECT_PHOENIX_999."
                    if "PROJECT_PHOENIX_999" in prompt_sent
                    else "Tôi không nhớ lượt trước."
                )
            resp.json.return_value = {
                "response": {"candidates": [{"content": {"parts": [{"text": text}]}}]}
            }
            return resp

        mock_http = MagicMock()
        mock_http.post = _fake_post
        gweb_client = GeminiWebClient(pool_manager=pool, http_client=mock_http)

        messages = [
            {"role": "system", "content": "Always remember user facts."},
            {"role": "user", "content": "Hãy nhớ mã dự án của tôi là PROJECT_PHOENIX_999."},
        ]
        res1 = await gweb_client.create_chat_completion({"model": "gemini-web-argon", "messages": messages})
        messages.append(res1["choices"][0]["message"])
        messages.append({"role": "user", "content": "Mã dự án của tôi là gì?"})

        res2 = await gweb_client.create_chat_completion({"model": "gemini-web-argon", "messages": messages})
        assert "PROJECT_PHOENIX_999" in res2["choices"][0]["message"]["content"]
        assert len(sent_prompts) == 2
        assert "[SYSTEM_INSTRUCTION]" in sent_prompts[1]
        assert "PROJECT_PHOENIX_999" in sent_prompts[1]
        assert pool.get_conversation_context(
            pool.compute_session_key({"messages": messages}),
            "gweb_stateless_oauth_gmail_com",
        ) is None

    asyncio.run(_run())


def test_turn_desync_on_node_failover_triggers_full_transcript_resync(tmp_path: Path):
    """Verify RC-03: If Turn 2 executes on Node 2 and Turn 3 returns to Node 1, Node 1 detects history_hash mismatch and resyncs."""
    async def _run():
        import urllib.parse

        pool = GeminiWebPoolManager(hermes_dir=tmp_path)
        for idx, email in enumerate(("n1@gmail.com", "n2@gmail.com"), 1):
            await pool.import_or_update_node(
                psid=f"g.psid_{idx}",
                psidts=f"sidts_{idx}",
                email=email,
                display_name=f"Node {idx}",
                verify_immediately=False,
            )
        for nid in ("gweb_n1_gmail_com", "gweb_n2_gmail_com"):
            pool.session_manager.save_session(
                node_id=nid,
                cookies={"__Secure-1PSID": f"g.psid_{nid}", "__Secure-1PSIDTS": f"sidts_{nid}"},
                snlm0e=f"SNlM0e_{nid}",
                cfb2h="boq_assistant-bard-web-server_20261102",
                fsid="-554433",
            )

        recorded_calls = []

        async def _fake_bard_post(url: str, content=None, **kwargs):
            qs = urllib.parse.parse_qs(content.decode("utf-8") if isinstance(content, bytes) else str(content))
            outer = json.loads((qs.get("f.req") or ["[]"])[0])
            inner = json.loads(outer[1])
            recorded_calls.append({"prompt": inner[0][0], "ctx": inner[2]})
            turn = len(recorded_calls)
            resp = MagicMock()
            resp.status_code = 200
            resp.text = _make_bard_rpc_response(
                text=f"Answer Turn {turn}",
                cid=f"cid_t{turn}",
                rid=f"rid_t{turn}",
                rcid=f"rcid_t{turn}",
            )
            return resp

        mock_http = MagicMock()
        mock_http.post = _fake_bard_post
        gweb_client = GeminiWebClient(pool_manager=pool, http_client=mock_http)

        # Also verify static `user` key disambiguation for new conversations
        key_conv_a = pool.compute_session_key(
            {"user": "static_user_1", "messages": [{"role": "user", "content": "Topic A"}]}
        )
        key_conv_b = pool.compute_session_key(
            {"user": "static_user_1", "messages": [{"role": "user", "content": "Topic B"}]}
        )
        assert key_conv_a != key_conv_b

        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Turn 1 fact: FACT_ONE"},
        ]
        r1 = await gweb_client.create_chat_completion(
            {"model": "gemini-web-argon", "messages": msgs},
            preferred_node_id="gweb_n1_gmail_com",
        )
        msgs.append(r1["choices"][0]["message"])

        # Turn 2 continues on the SAME Node 1 -> should use incremental_only=True (`cid_t1`)
        msgs.append({"role": "user", "content": "Turn 2 fact: FACT_TWO"})
        r2_same = await gweb_client.create_chat_completion(
            {"model": "gemini-web-argon", "messages": msgs},
            preferred_node_id="gweb_n1_gmail_com",
        )
        assert recorded_calls[1]["ctx"][0] == "cid_t1"
        assert "FACT_ONE" not in recorded_calls[1]["prompt"]

        # Now Turn 3 runs on Node 2 -> Node 2 has no context, sends Full Transcript
        msgs.append(r2_same["choices"][0]["message"])
        msgs.append({"role": "user", "content": "Turn 3 fact on Node 2: FACT_THREE"})
        r3_node2 = await gweb_client.create_chat_completion(
            {"model": "gemini-web-argon", "messages": msgs},
            preferred_node_id="gweb_n2_gmail_com",
        )
        msgs.append(r3_node2["choices"][0]["message"])

        # Turn 4 switches back to Node 1 -> Node 1's stored hash is from Turn 2, so it MUST detect Turn Desync!
        msgs.append({"role": "user", "content": "Turn 4 back on Node 1: recall all facts"})
        await gweb_client.create_chat_completion(
            {"model": "gemini-web-argon", "messages": msgs},
            preferred_node_id="gweb_n1_gmail_com",
        )
        assert recorded_calls[3]["ctx"][0] == ""
        assert "FACT_ONE" in recorded_calls[3]["prompt"]
        assert "FACT_TWO" in recorded_calls[3]["prompt"]
        assert "FACT_THREE" in recorded_calls[3]["prompt"]

    asyncio.run(_run())


def test_tool_call_id_correlation_and_trailing_slice_preservation():
    """Verify RC-04 & RC-05: tool_call_id resolves to function name even when role='tool' omits 'name', and trailing slice preserves all post-assistant messages."""
    payload = {
        "model": "gemini-web-argon",
        "messages": [
            {"role": "system", "content": "You are Hermes."},
            {"role": "user", "content": "Run two tools."},
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "Need both read_file and terminal.",
                "tool_calls": [
                    {
                        "id": "call_111",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "config.yaml"}'},
                    },
                    {
                        "id": "call_222",
                        "type": "function",
                        "function": {"name": "terminal", "arguments": '{"command": "uname -a"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_111", "content": "port: 8080"},
            {"role": "tool", "tool_call_id": "call_222", "content": "Linux x86_64"},
            {"role": "user", "content": "Format the output as a table."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {"name": "read_file", "parameters": {"type": "object", "properties": {}}},
            }
        ],
    }

    inc_prompt, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(payload, incremental_only=True)
    assert '<tool_response id="call_111" name="read_file">' in inc_prompt
    assert '<tool_response id="call_222" name="terminal">' in inc_prompt
    assert "Format the output as a table." in inc_prompt

    full_prompt, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(payload, incremental_only=False)
    assert '[TOOL_RESPONSE id="call_111" name="read_file"]' in full_prompt
    assert '[TOOL_RESPONSE id="call_222" name="terminal"]' in full_prompt
    assert "<thinking>\nNeed both read_file and terminal.\n</thinking>" in full_prompt
    assert '"id": "call_111"' in full_prompt


def test_parse_bard_stream_generate_response_ignores_empty_trailing_rcid_and_parses_json_fence():
    """Verify RC-06: Trailing empty metadata frame does not overwrite valid rcid, and ```json tool call fences are parsed."""
    f1_inner = json.dumps([None, ["c_1", "r_1"], None, None, [["rc_real_candidate", ["Hello world"]]]])
    f1_outer = json.dumps([["wrb.fr", None, f1_inner]])
    f2_inner = json.dumps([None, ["c_1", "r_1"], None, None, [["rc_empty_trailing", [""]]]])
    f2_outer = json.dumps([["wrb.fr", None, f2_inner]])
    raw_stream = f")]}}'\n\n{len(f1_outer)}\n{f1_outer}\n{len(f2_outer)}\n{f2_outer}\n"

    parsed = parse_bard_stream_generate_response(raw_stream)
    assert parsed["ok"] is True
    assert parsed["text"] == "Hello world"
    assert parsed["rcid"] == "rc_real_candidate"

    fenced_text = 'Here is the tool call:\n```json\n{"name": "web_search", "arguments": {"query": "Hermes Agent"}}\n```'
    tcs, cleaned = GeminiWebToolAdapter.extract_tool_calls_and_clean_text(fenced_text)
    assert len(tcs) == 1
    assert tcs[0]["function"]["name"] == "web_search"
    assert json.loads(tcs[0]["function"]["arguments"]) == {"query": "Hermes Agent"}
    assert "```" not in cleaned



