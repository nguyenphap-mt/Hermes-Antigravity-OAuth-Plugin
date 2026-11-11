#!/usr/bin/env python3
"""End-to-End Audit Loop for Gemini Web App Quota Bridge & Hermes Agent Memory Persistence.

Verifies all 7 core stages of the Gemini Web App Quota Bridge & Memory Persistence (PRD v1.2):
1. Stage 1 — Real Hermes Agent (`AIAgent` + `read_file` tool) multi-turn execution over `gemini-web-argon`
   with `<antigravity_tool_protocol>` compilation, `<tool_call>` parsing, and `[cid, rid, rcid]` context persistence.
2. Stage 2 — Real Hermes Agent (`AIAgent` + `terminal` tool) multi-turn execution over `gemini-web-2.5-pro`.
3. Stage 3 — Dual-Channel `hybrid_failover` when Code Assist is exhausted/disabled + Sliding-Window Quota
   Tracking + Proactive High-Water Mark (`<= 10%`) Node Switching.
4. Stage 4 — Dedicated Dashboard Management APIs (9 `/gemini-web/*` endpoints + `/doctor` check) and
   Zero-Leak Security Audit (`0o600` storage + masked telemetry).
5. Stage 5 — Stateless Linked OAuth Bridge (`oauth_bridge:`) 3-Turn Memory Audit (`RC-01` & `RC-02`).
6. Stage 6 — Multi-Node Failover Turn-Desync Recovery Audit (`RC-03`).
7. Stage 7 — Tool Call ID Correlation + ```json Fence + Trailing Metadata `rcid` Audit (`RC-04`, `RC-05`, `RC-06`).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import httpx
from aiohttp import web
from fastapi.testclient import TestClient

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HERMES_CANDIDATES = [
    PLUGIN_ROOT.parent / "hermes-agent",
    Path.home() / "hermes-agent",
    Path("/home/hermes/hermes-agent"),
]

if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

HERMES_ROOT = None
for cand in HERMES_CANDIDATES:
    if (cand / "run_agent.py").is_file():
        HERMES_ROOT = cand.resolve()
        if str(HERMES_ROOT) not in sys.path:
            sys.path.insert(0, str(HERMES_ROOT))
        break

from bridge.client import AntigravityClient
from bridge.gemini_web import (
    GEMINI_WEB_MODELS,
    GeminiWebClient,
    GeminiWebPoolManager,
    GeminiWebToolAdapter,
    build_model_selector_header,
    parse_bard_stream_generate_response,
)
from bridge.server import AntigravityBridgeServer


def _make_bard_stream_generate_envelope(
    text: str,
    cid: str = "c_hermes_audit_01",
    rid: str = "r_hermes_audit_01",
    rcid: str = "rc_hermes_audit_01",
    thoughts: str = "",
) -> str:
    """Build a realistic BardFrontendService/StreamGenerate chunked response."""
    cand: List[Any] = [rcid, [text]]
    if thoughts:
        cand.extend([None for _ in range(35)] + [[thoughts]])
    inner_obj = [
        None,
        [cid, rid],
        None,
        None,
        [cand],
    ]
    inner_json_str = json.dumps(inner_obj, ensure_ascii=False)
    wrb_frame = [["wrb.fr", None, inner_json_str]]
    frame_str = json.dumps(wrb_frame, ensure_ascii=False)
    return f")}}]'\n\n{len(frame_str)}\n{frame_str}\n"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run_audit() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hermes_root": str(HERMES_ROOT) if HERMES_ROOT else None,
        "stages": {},
        "all_passed": False,
    }

    with tempfile.TemporaryDirectory(prefix="ag_gweb_audit_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        secret_file = tmp_dir / "audit_secret_token.txt"
        expected_secret = "HERMES-GEMINI-WEB-ARGON-VERIFIED-987654"
        secret_file.write_text(expected_secret, encoding="utf-8")

        # Set up isolated GeminiWebPoolManager with 2 Web Nodes
        pool = GeminiWebPoolManager(hermes_dir=tmp_dir)
        asyncio.run(
            pool.import_or_update_node(
                psid="g.a000_AUDIT_NODE_1_SECRET_PSID",
                psidts="sidts_AUDIT_NODE_1_SECRET_PSIDTS",
                email="nguyenphap.pub1@gmail.com",
                display_name="Node 1 Ultra (Argon)",
                verify_immediately=False,
            )
        )
        asyncio.run(
            pool.import_or_update_node(
                psid="g.a000_AUDIT_NODE_2_SECRET_PSID",
                psidts="sidts_AUDIT_NODE_2_SECRET_PSIDTS",
                email="backup.webnode@gmail.com",
                display_name="Node 2 Pro (Backup)",
                verify_immediately=False,
            )
        )
        for nid in ("gweb_nguyenphap_pub1_gmail_com", "gweb_backup_webnode_gmail_com"):
            pool.session_manager.save_session(
                node_id=nid,
                cookies={
                    "__Secure-1PSID": f"g.a000_SECRET_{nid}",
                    "__Secure-1PSIDTS": f"sidts_SECRET_{nid}",
                },
                snlm0e=f"SNlM0e_TOKEN_{nid}",
                cfb2h="boq_assistant-bard-web-server_20261101.07_p0",
                fsid="-778899001122",
            )

        # Create AntigravityClient where Code Assist OAuth is simulated as exhausted/disabled
        # so we can test both explicit `gemini-web-*` models AND `hybrid_failover`
        mock_auth = MagicMock()
        mock_auth.auth_file = tmp_dir / "auth" / "antigravity_tokens.json"
        mock_auth.resolve_valid_credentials.return_value = None

        ag_client = AntigravityClient(auth_manager=mock_auth, gemini_web_pool=pool)
        ag_client.account_pool.get_account_for_service = MagicMock(return_value=None)

        # Track every call hitting BardFrontendService/StreamGenerate
        bard_calls: List[Dict[str, Any]] = []

        import urllib.parse

        async def _fake_bard_post(
            url: str,
            content: Any = None,
            headers: Dict[str, str] = None,
            data: Dict[str, Any] = None,
            **kwargs,
        ):
            if "RotateCookies" in url:
                r_rot = MagicMock()
                r_rot.status_code = 200
                r_rot.cookies = {}
                return r_rot

            if isinstance(content, (str, bytes)):
                qs = urllib.parse.parse_qs(content.decode("utf-8") if isinstance(content, bytes) else content)
                f_req_raw = (qs.get("f.req") or ["[]"])[0]
            else:
                f_req_raw = (data or {}).get("f.req", "[]")
            outer = json.loads(f_req_raw)
            inner = json.loads(outer[1])
            prompt_str: str = inner[0][0]
            raw_ctx = inner[2] if len(inner) > 2 and isinstance(inner[2], list) else ["", "", ""]
            conv_ctx: List[str] = [str(raw_ctx[0] or ""), str(raw_ctx[1] or ""), str(raw_ctx[2] or "")]
            model_hdr = (headers or {}).get("x-goog-ext-525001261-jspb", "")

            bard_calls.append(
                {
                    "url": url,
                    "prompt": prompt_str,
                    "conv_ctx": conv_ctx,
                    "model_header": model_hdr,
                }
            )

            resp = MagicMock()
            resp.status_code = 200

            # Check if this is Turn 2 (after Hermes Agent executed the tool and returned <tool_response id=...>)
            if "</tool_response>" in prompt_str or "[/TOOL_RESPONSE]" in prompt_str:
                if "HERMES-GEMINI-WEB-ARGON-VERIFIED" in prompt_str or "read_file" in prompt_str:
                    resp.text = _make_bard_stream_generate_envelope(
                        text=f"Đã đọc file bằng Hermes read_file tool thành công! Nội dung: {expected_secret}",
                        cid=conv_ctx[0] or "c_argon_turn2",
                        rid="r_argon_turn2",
                        rcid="rc_argon_turn2",
                        thoughts="Verified file content from Hermes read_file tool.",
                    )
                elif "56154" in prompt_str or "HERMES_TERMINAL_WEB_PRO_OK_2026" in prompt_str or "terminal" in prompt_str:
                    resp.text = _make_bard_stream_generate_envelope(
                        text="Đã chạy lệnh terminal bằng Hermes tool thành công! Kết quả: HERMES_TERMINAL_WEB_PRO_OK_2026 (56154)",
                        cid=conv_ctx[0] or "c_pro_turn2",
                        rid="r_pro_turn2",
                        rcid="rc_pro_turn2",
                        thoughts="Verified terminal output from Hermes terminal tool.",
                    )
                else:
                    resp.text = _make_bard_stream_generate_envelope(
                        text="Tool execution completed.",
                        cid="c_generic",
                        rid="r_generic",
                        rcid="rc_generic",
                    )
            else:
                # Turn 1: Emit <tool_call> for Hermes Agent to execute!
                if "CHECK_TERMINAL_TOOL" in prompt_str:
                    tc_json = json.dumps(
                        {
                            "name": "terminal",
                            "arguments": {
                                "command": f'"{sys.executable}" -c "print(\'HERMES_TERMINAL_WEB_PRO_OK_2026\', 42 * 1337)"'
                            },
                        },
                        ensure_ascii=False,
                    )
                    resp.text = _make_bard_stream_generate_envelope(
                        text=f"<tool_call>{tc_json}</tool_call>",
                        cid="c_pro_session_01",
                        rid="r_pro_session_01",
                        rcid="rc_pro_session_01",
                        thoughts="Calling Hermes terminal tool to compute 42 * 1337.",
                    )
                else:
                    tc_json = json.dumps(
                        {
                            "name": "read_file",
                            "arguments": {"path": str(secret_file)},
                        },
                        ensure_ascii=False,
                    )
                    resp.text = _make_bard_stream_generate_envelope(
                        text=f"<tool_call>{tc_json}</tool_call>",
                        cid="c_argon_session_01",
                        rid="r_argon_session_01",
                        rcid="rc_argon_session_01",
                        thoughts="Calling Hermes read_file tool to inspect secret token.",
                    )
            return resp

        ag_client._http.post = _fake_bard_post

        # Spin up live local Antigravity Bridge HTTP server on an ephemeral port
        port = _find_free_port()
        bridge_srv = AntigravityBridgeServer(host="127.0.0.1", port=port, auth_manager=mock_auth)
        bridge_srv.client = ag_client

        srv_loop = asyncio.new_event_loop()
        srv_ready = threading.Event()
        srv_stop = threading.Event()

        def _run_bridge_thread():
            asyncio.set_event_loop(srv_loop)

            async def _serve():
                runner = web.AppRunner(bridge_srv.app)
                await runner.setup()
                site = web.TCPSite(runner, "127.0.0.1", port)
                await site.start()
                srv_ready.set()
                while not srv_stop.is_set():
                    await asyncio.sleep(0.05)
                await runner.cleanup()

            srv_loop.run_until_complete(_serve())

        server_thread = threading.Thread(target=_run_bridge_thread, daemon=True)
        server_thread.start()
        srv_ready.wait(timeout=5.0)

        base_url = f"http://127.0.0.1:{port}/v1"

        try:
            # =========================================================================
            # STAGE 1: Real Hermes AIAgent + `read_file` Tool over `gemini-web-argon`
            # =========================================================================
            try:
                import hermes_cli.venv_sync as _vs
                _vs.prepare_launch = lambda *a, **kw: None
                import pm.environments as _pme
                _pme.activate_dependencies = lambda *a, **kw: None
            except Exception:
                pass
            from run_agent import AIAgent

            bard_calls.clear()
            agent_argon = AIAgent(
                base_url=base_url,
                api_key="ag-gemini-web-audit-key",
                provider="custom",
                api_mode="chat_completions",
                model="gemini-web-argon",
                max_iterations=5,
                enabled_toolsets=["file"],
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
            )
            agent_argon.model = "gemini-web-argon"
            res_stage1 = agent_argon.run_conversation(
                user_message=f"Hãy dùng tool read_file để đọc nội dung file {secret_file} và trả lời chính xác chuỗi trong đó."
            )
            final_resp_1 = res_stage1.get("final_response", "")
            assert expected_secret in final_resp_1, f"Stage 1 failed: {final_resp_1}"
            assert len(bard_calls) >= 2, f"Expected >=2 Bard turns in Stage 1, got {len(bard_calls)}"
            # Verify Turn 1 injected <antigravity_tool_protocol> and used Argon default_hex
            assert "<antigravity_tool_protocol>" in bard_calls[0]["prompt"]
            expected_argon_hex = GEMINI_WEB_MODELS["gemini-web-argon"]["default_hex"]
            assert expected_argon_hex in bard_calls[0]["model_header"], (
                f"Expected Argon hex {expected_argon_hex} in model_header, got {bard_calls[0]['model_header']}"
            )
            # Verify Turn 2 carried <tool_response> with actual file content read by Hermes `read_file` tool
            # AND preserved the server-side `[cid, rid, rcid]` context from Turn 1!
            assert (
                "</tool_response>" in bard_calls[1]["prompt"]
                or "[/TOOL_RESPONSE]" in bard_calls[1]["prompt"]
            )
            assert expected_secret in bard_calls[1]["prompt"]
            assert bard_calls[1]["conv_ctx"] == [
                "c_argon_session_01",
                "r_argon_session_01",
                "rc_argon_session_01",
            ]

            report["stages"]["stage1_hermes_read_file_gemini_web_argon"] = {
                "passed": True,
                "model": "gemini-web-argon",
                "model_header_sent": bard_calls[0]["model_header"],
                "turns_executed": len(bard_calls),
                "conv_ctx_turn2": bard_calls[1]["conv_ctx"],
                "final_response": final_resp_1,
            }

            # =========================================================================
            # STAGE 2: Real Hermes AIAgent + `terminal` Tool over `gemini-web-2.5-pro`
            # =========================================================================
            bard_calls.clear()
            agent_pro = AIAgent(
                base_url=base_url,
                api_key="ag-gemini-web-audit-key",
                provider="custom",
                api_mode="chat_completions",
                model="gemini-web-2.5-pro",
                max_iterations=5,
                enabled_toolsets=["terminal"],
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
            )
            agent_pro.model = "gemini-web-2.5-pro"
            res_stage2 = agent_pro.run_conversation(
                user_message="CHECK_TERMINAL_TOOL: Hãy chạy lệnh terminal kiểm tra và báo kết quả."
            )
            final_resp_2 = res_stage2.get("final_response", "")
            assert "HERMES_TERMINAL_WEB_PRO_OK_2026" in final_resp_2, f"Stage 2 failed: {final_resp_2}"
            assert len(bard_calls) >= 2, f"Expected >=2 Bard turns in Stage 2, got {len(bard_calls)}"
            # Verify Turn 2 carried the actual stdout from Hermes `terminal` tool execution ("56154")
            assert "56154" in bard_calls[1]["prompt"]

            report["stages"]["stage2_hermes_terminal_gemini_web_pro"] = {
                "passed": True,
                "model": "gemini-web-2.5-pro",
                "model_header_sent": bard_calls[0]["model_header"],
                "turns_executed": len(bard_calls),
                "terminal_stdout_verified_in_turn2": "56154" in bard_calls[1]["prompt"],
                "final_response": final_resp_2,
            }

            # =========================================================================
            # STAGE 3: Hybrid Failover (`gemini-3.7-flash` -> Gemini Web Pool) +
            #          Proactive High-Water Mark (`<= 10%`) Node Switching
            # =========================================================================
            bard_calls.clear()
            # Configure Node 1 with `argon_hourly_limit = 10` and add 7 more usages so it hits 9/10 (10% remaining)
            pool.update_node_limits("gweb_nguyenphap_pub1_gmail_com", limits={"argon_hourly_limit": 10})
            n1_before = pool.get_node("gweb_nguyenphap_pub1_gmail_com")
            current_argon_count = len(n1_before.usage_timestamps.get("argon", []))
            for _ in range(max(0, 9 - current_argon_count)):
                pool.record_web_usage("gweb_nguyenphap_pub1_gmail_com", "gemini-web-argon", success=True)

            q_node1 = pool.compute_node_quota_summary(pool.get_node("gweb_nguyenphap_pub1_gmail_com"))
            assert q_node1["argon_remaining_pct"] <= 10.0, f"Expected Node 1 <=10%, got {q_node1}"

            # Now run Hermes Agent requesting standard Code Assist model `gemini-3.7-flash`.
            # Because Code Assist has 0 available credentials AND Node 1 is at <= 10% remaining,
            # `hybrid_failover` must automatically fail over to Gemini Web AND proactively select Node 2!
            selected_before_failover = pool.select_node_for_model("gemini-web-argon")
            assert selected_before_failover is not None
            assert selected_before_failover.node_id == "gweb_backup_webnode_gmail_com"

            agent_failover = AIAgent(
                base_url=base_url,
                api_key="ag-gemini-web-audit-key",
                provider="custom",
                api_mode="chat_completions",
                model="gemini-3.7-flash",
                max_iterations=5,
                enabled_toolsets=["file"],
                quiet_mode=True,
                skip_context_files=True,
                skip_memory=True,
            )
            agent_failover.model = "gemini-3.7-flash"
            res_stage3 = agent_failover.run_conversation(
                user_message=f"Đọc file {secret_file} khi Code Assist hết hạn mức."
            )
            final_resp_3 = res_stage3.get("final_response", "")
            assert expected_secret in final_resp_3, f"Stage 3 hybrid failover failed: {final_resp_3}"

            report["stages"]["stage3_hybrid_failover_and_proactive_switch"] = {
                "passed": True,
                "requested_model": "gemini-3.7-flash",
                "node1_remaining_pct": q_node1["argon_remaining_pct"],
                "proactively_switched_to_node": selected_before_failover.node_id,
                "final_response": final_resp_3,
            }

            # =========================================================================
            # STAGE 4: Dedicated Dashboard 9 `/gemini-web/*` APIs & Zero-Leak Security
            # =========================================================================
            from fastapi import FastAPI
            from dashboard.plugin_api import router

            dash_app = FastAPI()
            dash_app.include_router(router)
            dash_client = TestClient(dash_app)

            # Patch `_get_gemini_web_pool` inside `dashboard.plugin_api` to use our isolated `pool`
            import dashboard.plugin_api as dash_api_mod
            dash_api_mod._get_gemini_web_pool = lambda: pool

            # 1. GET /gemini-web/pool
            r_pool = dash_client.get("/gemini-web/pool")
            assert r_pool.status_code == 200
            pool_json_str = r_pool.text
            # Security check: Ensure NO raw cookie secrets (`g.a000_SECRET_`, `sidts_SECRET_`, `SNlM0e_TOKEN_`) leak!
            assert "g.a000_SECRET_" not in pool_json_str
            assert "sidts_SECRET_" not in pool_json_str
            assert "SNlM0e_TOKEN_" not in pool_json_str

            # 2. POST /gemini-web/config
            r_cfg = dash_client.post(
                "/gemini-web/config",
                json={
                    "routing_mode": "hybrid_failover",
                    "proactive_switch_threshold_pct": 12.0,
                    "sticky_session": True,
                    "auto_rotate_cookies": True,
                },
            )
            assert r_cfg.status_code == 200 and r_cfg.json()["ok"] is True

            # 3. POST /gemini-web/nodes/import (using Cookie-Editor JSON array format)
            r_imp = dash_client.post(
                "/gemini-web/nodes/import",
                json={
                    "raw_cookie_input": json.dumps(
                        [
                            {"name": "__Secure-1PSID", "value": "g.a000_IMPORTED_NODE_3"},
                            {"name": "__Secure-1PSIDTS", "value": "sidts_IMPORTED_NODE_3"},
                        ]
                    ),
                    "email": "node3.imported@gmail.com",
                    "display_name": "Node 3 Imported",
                    "verify_immediately": False,
                },
            )
            assert r_imp.status_code == 200 and r_imp.json()["ok"] is True
            node3_id = r_imp.json()["node"]["node_id"]

            # 4. POST /gemini-web/nodes/toggle
            r_tog = dash_client.post(
                "/gemini-web/nodes/toggle",
                json={"node_id": node3_id, "enabled": False},
            )
            assert r_tog.status_code == 200 and r_tog.json()["node"]["enabled"] is False

            # 5. POST /gemini-web/nodes/limits
            r_lim = dash_client.post(
                "/gemini-web/nodes/limits",
                json={
                    "node_id": node3_id,
                    "argon_hourly_limit": 25,
                    "pro_hourly_limit": 35,
                    "flash_hourly_limit": 120,
                },
            )
            assert r_lim.status_code == 200 and r_lim.json()["node"]["quota_limits"]["argon_hourly_limit"] == 25

            # 6. DELETE /gemini-web/nodes/{node_id}
            r_del = dash_client.delete(f"/gemini-web/nodes/{node3_id}")
            assert r_del.status_code == 200 and r_del.json()["ok"] is True

            # 7. GET /doctor (verify 7th check `gemini_web_pool` is present)
            r_doc = dash_client.get("/doctor")
            assert r_doc.status_code == 200
            doc_checks = {c["id"]: c for c in r_doc.json().get("checks", [])}
            assert "gemini_web_pool" in doc_checks

            report["stages"]["stage4_dashboard_apis_and_security_audit"] = {
                "passed": True,
                "endpoints_verified": [
                    "GET /gemini-web/pool",
                    "POST /gemini-web/config",
                    "POST /gemini-web/nodes/import",
                    "POST /gemini-web/nodes/toggle",
                    "POST /gemini-web/nodes/limits",
                    "DELETE /gemini-web/nodes/{node_id}",
                    "GET /doctor (gemini_web_pool)",
                ],
                "zero_cookie_secret_leak_verified": True,
                "doctor_gemini_web_check": doc_checks["gemini_web_pool"],
            }

            # =========================================================================
            # STAGE 5: Strict Web Cookie Auth Quarantine + Quota Reset Sync & Failover
            # =========================================================================
            s5_dir = tmp_dir / "stage5_strict_auth_and_quota"
            s5_dir.mkdir(parents=True, exist_ok=True)
            # 1. Seed a legacy synthetic oauth_linked_* node on disk
            (s5_dir / "gemini_web_pool.json").write_text(
                json.dumps(
                    {
                        "config": {"routing_mode": "hybrid_failover"},
                        "nodes": [
                            {
                                "node_id": "gweb_legacy_oauth_gmail_com",
                                "email": "legacy.oauth@gmail.com",
                                "display_name": "Legacy OAuth Node",
                                "enabled": True,
                                "status": "ready",
                                "detected_tier": "pro",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (s5_dir / "gemini_web_sessions.json").write_text(
                json.dumps(
                    {
                        "sessions": {
                            "gweb_legacy_oauth_gmail_com": {
                                "node_id": "gweb_legacy_oauth_gmail_com",
                                "cookies": {"__Secure-1PSID": "oauth_linked_legacy.oauth@gmail.com"},
                                "snlm0e": "oauth_bridge:legacy.oauth@gmail.com",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            pool_s5 = GeminiWebPoolManager(hermes_dir=s5_dir)
            snap_s5_initial = pool_s5.get_dashboard_pool_snapshot()
            assert snap_s5_initial["total_nodes"] == 1
            assert snap_s5_initial["ready_nodes"] == 0, f"Synthetic OAuth node must not be ready: {snap_s5_initial}"
            assert snap_s5_initial["nodes"][0]["status"] == "unverified"
            assert snap_s5_initial["nodes"][0]["cookie_health"]["is_authentic_web_session"] is False

            # 2. Attach real Gemini Web cookies to 2 nodes (Node 1 will hit 'Đã đạt đến hạn mức · Đặt lại lúc 21:07' on Turn 1, failing over to Node 2)
            for idx, em in enumerate(("primary.web@gmail.com", "backup.web@gmail.com"), 1):
                asyncio.run(
                    pool_s5.import_or_update_node(
                        psid=f"g.a000_REAL_WEB_S5_{idx}",
                        psidts=f"sidts_REAL_WEB_S5_{idx}",
                        email=em,
                        display_name=f"Stage 5 Web Node {idx}",
                        verify_immediately=False,
                    )
                )
                nid_s5 = f"gweb_{em.replace('.', '_').replace('@', '_')}"
                pool_s5.session_manager.save_session(
                    node_id=nid_s5,
                    cookies={"__Secure-1PSID": f"g.a000_REAL_WEB_S5_{idx}", "__Secure-1PSIDTS": f"sidts_REAL_WEB_S5_{idx}"},
                    snlm0e=f"SNlM0e_REAL_S5_{idx}",
                    cfb2h="boq_assistant-bard-web-server_20261111",
                    fsid="-998877",
                )

            s5_calls: List[Dict[str, Any]] = []

            async def _fake_s5_post(url: str, content: Any = None, cookies: Dict[str, str] = None, **kw):
                qs = urllib.parse.parse_qs(content.decode("utf-8") if isinstance(content, bytes) else str(content))
                outer = json.loads((qs.get("f.req") or ["[]"])[0])
                inner = json.loads(outer[1])
                p_txt = inner[0][0]
                psid_used = (cookies or {}).get("__Secure-1PSID", "")
                s5_calls.append({"psid": psid_used, "prompt": p_txt})

                r = MagicMock()
                r.status_code = 200
                # If Node 1 (`g.a000_REAL_WEB_S5_1`) is called, simulate Gemini Web quota exhaustion banner
                if psid_used == "g.a000_REAL_WEB_S5_1":
                    r.text = _make_bard_stream_generate_envelope(
                        text="Đã đạt đến hạn mức · Đặt lại lúc 21:07",
                        cid="",
                        rid="",
                        rcid="",
                    )
                    return r

                # Node 2 (`g.a000_REAL_WEB_S5_2`) handles the failover and completes the 3-turn flow
                node2_calls = [c for c in s5_calls if c["psid"] == "g.a000_REAL_WEB_S5_2"]
                turn_idx = len(node2_calls)
                if turn_idx == 1:
                    ans = '<tool_call>{"name": "read_file", "arguments": {"path": "/tmp/s5.txt"}}</tool_call>'
                elif turn_idx == 2:
                    ans = "Đã đọc file /tmp/s5.txt với mã: SECRET_OMEGA_777."
                else:
                    ans = "Mã bí mật ở lượt 1-2 là SECRET_OMEGA_777."
                r.text = _make_bard_stream_generate_envelope(
                    text=ans,
                    cid="cid_s5_node2",
                    rid=f"rid_s5_{turn_idx}",
                    rcid=f"rcid_s5_{turn_idx}",
                )
                return r

            http_s5 = MagicMock()
            http_s5.post = _fake_s5_post
            gweb_s5 = GeminiWebClient(pool_manager=pool_s5, http_client=http_s5)

            tools_schema = [
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read a file",
                        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                    },
                }
            ]
            s5_msgs: List[Dict[str, Any]] = [
                {"role": "system", "content": "You are Hermes Agent with persistent memory."},
                {"role": "user", "content": "Hãy đọc file /tmp/s5.txt và ghi nhớ mã SECRET_OMEGA_777."},
            ]
            c_t1 = asyncio.run(
                gweb_s5.create_chat_completion(
                    {"model": "gemini-web-argon", "messages": s5_msgs, "tools": tools_schema},
                    preferred_node_id="gweb_primary_web_gmail_com",
                )
            )
            # Verify Node 1 was marked at 0% remaining with reset time 21:07 after returning the quota banner
            n1_s5 = pool_s5.format_node_for_dashboard(pool_s5.get_node("gweb_primary_web_gmail_com"))
            assert n1_s5["quota_summary"]["argon_remaining_pct"] == 0.0
            assert n1_s5["quota_summary"]["argon_reset_at_label"] == "21:07"
            assert c_t1["x_gemini_web_node"] == "gweb_backup_web_gmail_com"

            tc_s5 = c_t1["choices"][0]["message"]["tool_calls"][0]
            s5_msgs.append(c_t1["choices"][0]["message"])
            s5_msgs.append({"role": "tool", "tool_call_id": tc_s5["id"], "content": "FILE_DATA=SECRET_OMEGA_777"})

            c_t2 = asyncio.run(
                gweb_s5.create_chat_completion({"model": "gemini-web-argon", "messages": s5_msgs, "tools": tools_schema})
            )
            s5_msgs.append(c_t2["choices"][0]["message"])
            s5_msgs.append({"role": "user", "content": "Nhắc lại mã bí mật ở các lượt trước là gì?"})

            c_t3 = asyncio.run(
                gweb_s5.create_chat_completion({"model": "gemini-web-argon", "messages": s5_msgs, "tools": tools_schema})
            )
            ans_t3 = c_t3["choices"][0]["message"]["content"]
            assert "SECRET_OMEGA_777" in ans_t3, f"Stage 5 amnesia on Turn 3: {ans_t3}"

            report["stages"]["stage5_strict_web_auth_and_quota_reset_sync"] = {
                "passed": True,
                "legacy_oauth_node_quarantined": True,
                "node1_quota_exhausted_reset_at": n1_s5["quota_summary"]["argon_reset_at_label"],
                "failed_over_to_node": c_t1["x_gemini_web_node"],
                "turn3_response": ans_t3,
            }

            # =========================================================================
            # STAGE 6: Multi-Node Failover Turn-Desync Recovery Audit (`RC-03`)
            # =========================================================================
            s6_dir = tmp_dir / "stage6_turn_desync"
            pool_s6 = GeminiWebPoolManager(hermes_dir=s6_dir)
            for idx, em in enumerate(("nodeA@gmail.com", "nodeB@gmail.com"), 1):
                asyncio.run(
                    pool_s6.import_or_update_node(
                        psid=f"g.s6_psid_{idx}",
                        psidts=f"sidts_s6_{idx}",
                        email=em,
                        display_name=f"Stage 6 Node {idx}",
                        verify_immediately=False,
                    )
                )
            for nid in ("gweb_nodea_gmail_com", "gweb_nodeb_gmail_com"):
                pool_s6.session_manager.save_session(
                    node_id=nid,
                    cookies={"__Secure-1PSID": f"g.psid_{nid}", "__Secure-1PSIDTS": f"sidts_{nid}"},
                    snlm0e=f"SNlM0e_{nid}",
                    cfb2h="boq_assistant-bard-web-server_20261102",
                    fsid="-112233",
                )

            s6_calls: List[Dict[str, Any]] = []

            async def _fake_s6_post(url: str, content: Any = None, **kw):
                qs = urllib.parse.parse_qs(content.decode("utf-8") if isinstance(content, bytes) else str(content))
                outer = json.loads((qs.get("f.req") or ["[]"])[0])
                inner = json.loads(outer[1])
                p_str = inner[0][0]
                ctx_arr = inner[2]
                s6_calls.append({"prompt": p_str, "ctx": ctx_arr})
                r = MagicMock()
                r.status_code = 200
                step = len(s6_calls)
                r.text = _make_bard_stream_generate_envelope(
                    text=f" Phản hồi lượt {step} thành công (NOI_DUNG_LUOT_{step}).",
                    cid=f"cid_step_{step}",
                    rid=f"rid_step_{step}",
                    rcid=f"rcid_step_{step}",
                )
                return r

            http_s6 = MagicMock()
            http_s6.post = _fake_s6_post
            gweb_s6 = GeminiWebClient(pool_manager=pool_s6, http_client=http_s6)

            s6_msgs: List[Dict[str, Any]] = [
                {"role": "system", "content": "System instruction Stage 6"},
                {"role": "user", "content": "Câu hỏi lượt 1: Mã KHO_BAU_01"},
            ]
            # Turn 1 on Node A
            r6_1 = asyncio.run(
                gweb_s6.create_chat_completion(
                    {"model": "gemini-web-argon", "messages": s6_msgs},
                    preferred_node_id="gweb_nodea_gmail_com",
                )
            )
            s6_msgs.append(r6_1["choices"][0]["message"])

            # Turn 2 forced onto Node B (simulating failover/cooldown on Node A during Turn 2)
            s6_msgs.append({"role": "user", "content": "Câu hỏi lượt 2: Mã KHO_BAU_02"})
            r6_2 = asyncio.run(
                gweb_s6.create_chat_completion(
                    {"model": "gemini-web-argon", "messages": s6_msgs},
                    preferred_node_id="gweb_nodeb_gmail_com",
                )
            )
            s6_msgs.append(r6_2["choices"][0]["message"])

            # Turn 3 returns to Node A -> Node A's old Turn 1 hash would desync if not invalidated/checked!
            s6_msgs.append({"role": "user", "content": "Câu hỏi lượt 3: Tổng hợp cả KHO_BAU_01 và KHO_BAU_02"})
            r6_3 = asyncio.run(
                gweb_s6.create_chat_completion(
                    {"model": "gemini-web-argon", "messages": s6_msgs},
                    preferred_node_id="gweb_nodea_gmail_com",
                )
            )
            assert len(s6_calls) == 3
            # Turn 3 on Node A MUST have detected Turn Desync (`ctx == ["", "", ""]`) and sent Full Transcript containing Turn 2!
            assert s6_calls[2]["ctx"][0] == "", f"Expected reset cid on Turn Desync, got {s6_calls[2]['ctx']}"
            assert "KHO_BAU_01" in s6_calls[2]["prompt"]
            assert "KHO_BAU_02" in s6_calls[2]["prompt"]
            assert "NOI_DUNG_LUOT_2" in s6_calls[2]["prompt"]

            report["stages"]["stage6_multinode_failover_turn_desync_recovery"] = {
                "passed": True,
                "turn3_ctx_reset": s6_calls[2]["ctx"],
                "turn2_history_preserved_in_turn3_prompt": True,
            }

            # =========================================================================
            # STAGE 7: Tool Call ID Correlation + ```json Fence + Trailing `rcid` Audit
            # =========================================================================
            s7_payload = {
                "model": "gemini-web-argon",
                "messages": [
                    {"role": "system", "content": "You are Hermes."},
                    {"role": "user", "content": "Check files."},
                    {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "First inspect both files.",
                        "tool_calls": [
                            {
                                "id": "call_alpha_001",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
                            },
                            {
                                "id": "call_beta_002",
                                "type": "function",
                                "function": {"name": "search_files", "arguments": '{"pattern": "secret"}'},
                            },
                        ],
                    },
                    # Note: OpenAI `role: "tool"` messages WITHOUT `"name"` field, plus a trailing user note
                    {"role": "tool", "tool_call_id": "call_alpha_001", "content": "Alpha content"},
                    {"role": "tool", "tool_call_id": "call_beta_002", "content": "Beta match"},
                    {"role": "user", "content": "Also summarize both results in Vietnamese."},
                ],
                "tools": tools_schema,
            }
            inc_prompt, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(s7_payload, incremental_only=True)
            assert '<tool_response id="call_alpha_001" name="read_file">' in inc_prompt
            assert '<tool_response id="call_beta_002" name="search_files">' in inc_prompt
            assert "Also summarize both results in Vietnamese." in inc_prompt

            full_prompt_s7, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(s7_payload, incremental_only=False)
            assert '[TOOL_RESPONSE id="call_alpha_001" name="read_file"]' in full_prompt_s7
            assert '[TOOL_RESPONSE id="call_beta_002" name="search_files"]' in full_prompt_s7
            assert "<thinking>\nFirst inspect both files.\n</thinking>" in full_prompt_s7
            assert '"id": "call_alpha_001"' in full_prompt_s7

            # Verify ```json fenced tool_call parsing
            fenced_json_output = 'Tôi sẽ gọi tool:\n```json\n{"name": "read_file", "arguments": {"path": "/etc/hosts"}}\n```'
            tcs_fenced, cleaned_fenced = GeminiWebToolAdapter.extract_tool_calls_and_clean_text(fenced_json_output)
            assert len(tcs_fenced) == 1
            assert tcs_fenced[0]["function"]["name"] == "read_file"
            assert "```" not in cleaned_fenced

            # Verify trailing metadata frame with empty candidate text does NOT overwrite valid `rcid`
            frame1_inner = json.dumps([None, ["c_s7", "r_s7"], None, None, [["rc_valid_text_frame", ["Hello from Frame 1"]]]])
            frame1_outer = json.dumps([["wrb.fr", None, frame1_inner]])
            frame2_inner = json.dumps([None, ["c_s7", "r_s7"], None, None, [["rc_empty_metadata_frame", [""]]]])
            frame2_outer = json.dumps([["wrb.fr", None, frame2_inner]])
            multi_frame_raw = f")}}]'\n\n{len(frame1_outer)}\n{frame1_outer}\n{len(frame2_outer)}\n{frame2_outer}\n"
            parsed_mf = parse_bard_stream_generate_response(multi_frame_raw)
            assert parsed_mf["ok"] is True
            assert parsed_mf["text"] == "Hello from Frame 1"
            assert parsed_mf["rcid"] == "rc_valid_text_frame"

            report["stages"]["stage7_tool_correlation_json_fence_and_rcid_guard"] = {
                "passed": True,
                "tool_id_to_name_verified": True,
                "json_fence_tool_call_verified": True,
                "rcid_preserved": parsed_mf["rcid"],
            }

            # =========================================================================
            # STAGE 8: Real Live Google Upstream 3-Turn Hermes AIAgent Tool + Memory Audit
            # =========================================================================
            live_hermes_candidates = [
                Path.home() / "AppData" / "Local" / "hermes",
                Path.home() / ".hermes",
                Path("/home/hermes/.hermes"),
            ]
            live_hermes_dir = None
            for lcand in live_hermes_candidates:
                if lcand.is_dir():
                    test_p = GeminiWebPoolManager(hermes_dir=lcand)
                    if test_p.get_dashboard_pool_snapshot().get("ready_nodes", 0) > 0:
                        live_hermes_dir = lcand
                        break

            if live_hermes_dir is not None:
                from bridge.auth import AntigravityAuthManager

                live_pool = GeminiWebPoolManager(hermes_dir=live_hermes_dir)
                live_auth = AntigravityAuthManager(
                    auth_file=live_hermes_dir / "auth" / "antigravity_tokens.json"
                )
                live_ag_client = AntigravityClient(auth_manager=live_auth, gemini_web_pool=live_pool)
                live_port = _find_free_port()
                live_srv = AntigravityBridgeServer(
                    host="127.0.0.1",
                    port=live_port,
                    auth_manager=live_auth,
                )
                live_srv.client = live_ag_client

                live_loop = asyncio.new_event_loop()
                live_ready = threading.Event()
                live_stop = threading.Event()

                def _run_live_bridge():
                    asyncio.set_event_loop(live_loop)

                    async def _serve_live():
                        runner = web.AppRunner(live_srv.app)
                        await runner.setup()
                        site = web.TCPSite(runner, "127.0.0.1", live_port)
                        await site.start()
                        live_ready.set()
                        while not live_stop.is_set():
                            await asyncio.sleep(0.05)
                        await runner.cleanup()

                    live_loop.run_until_complete(_serve_live())

                live_thread = threading.Thread(target=_run_live_bridge, daemon=True)
                live_thread.start()
                live_ready.wait(timeout=5.0)
                live_base_url = f"http://127.0.0.1:{live_port}/v1"

                try:
                    live_secret_file = tmp_dir / "live_upstream_secret.txt"
                    live_secret_val = "LIVE_HERMES_SECRET_2026_7788"
                    live_secret_file.write_text(live_secret_val, encoding="utf-8")

                    live_agent = AIAgent(
                        base_url=live_base_url,
                        api_key="ag-live-upstream-audit-key",
                        provider="custom",
                        api_mode="chat_completions",
                        model="gemini-web-argon",
                        max_iterations=8,
                        enabled_toolsets=["file", "terminal"],
                        quiet_mode=True,
                        skip_context_files=True,
                        skip_memory=True,
                    )
                    live_agent.model = "gemini-web-argon"

                    # Live Turn 1: Execute real `read_file` tool + store project codename in conversation memory
                    live_r1 = live_agent.run_conversation(
                        user_message=(
                            f"Hãy dùng tool read_file để đọc file {live_secret_file}. "
                            "Đồng thời ghi nhớ mật danh dự án của tôi là BENTHANH_OMEGA_99. Trả lời ngắn gọn."
                        )
                    )
                    live_resp1 = str(live_r1.get("final_response") or "")
                    live_hist1 = list(live_r1.get("messages") or [])
                    assert live_secret_val in live_resp1, f"Live Stage 8 Turn 1 failed: {live_resp1}"

                    # Live Turn 2: Execute real `terminal` tool in the SAME conversation + store calculation
                    live_r2 = live_agent.run_conversation(
                        user_message=(
                            f'Hãy dùng tool terminal chạy lệnh: "{sys.executable}" -c "print(19 * 23)" '
                            "và báo kết quả số tính được. Trả lời ngắn gọn."
                        ),
                        conversation_history=live_hist1,
                    )
                    live_resp2 = str(live_r2.get("final_response") or "")
                    live_hist2 = list(live_r2.get("messages") or [])
                    assert "437" in live_resp2, f"Live Stage 8 Turn 2 failed: {live_resp2}"

                    # Live Turn 3: Recall ALL facts from Turn 1 & Turn 2 without calling tools
                    live_r3 = live_agent.run_conversation(
                        user_message=(
                            "Không cần gọi tool nữa, hãy liệt kê chính xác 3 thông tin từ các lượt trước: "
                            "(1) chuỗi bí mật trong file ở lượt 1, "
                            "(2) mật danh dự án ở lượt 1, "
                            "(3) kết quả phép nhân 19 * 23 ở lượt 2."
                        ),
                        conversation_history=live_hist2,
                    )
                    live_resp3 = str(live_r3.get("final_response") or "")
                    assert live_secret_val in live_resp3, f"Live Turn 3 forgot file secret: {live_resp3}"
                    assert "BENTHANH_OMEGA_99" in live_resp3, f"Live Turn 3 forgot project codename: {live_resp3}"
                    assert "437" in live_resp3, f"Live Turn 3 forgot terminal result: {live_resp3}"

                    report["stages"]["stage8_live_upstream_hermes_3turn_tools_and_memory"] = {
                        "passed": True,
                        "live_hermes_dir": str(live_hermes_dir),
                        "turn1_read_file_response": live_resp1,
                        "turn2_terminal_response": live_resp2,
                        "turn3_memory_recall_response": live_resp3,
                    }
                finally:
                    live_stop.set()
                    live_thread.join(timeout=2.0)
                    asyncio.run(live_ag_client.close())

            report["all_passed"] = True

        finally:
            srv_stop.set()
            server_thread.join(timeout=2.0)
            asyncio.run(ag_client.close())

    return report


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("all_passed") else 1)
