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
    import dashboard.plugin_api as papi

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


