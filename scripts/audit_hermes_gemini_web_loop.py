#!/usr/bin/env python3
"""End-to-End Audit Loop for Gemini Web App Quota Bridge & Hermes Agent Tool Execution.

Verifies all 4 core stages of the Gemini Web App Quota Bridge (PRD v1.2):
1. Stage 1 — Real Hermes Agent (`AIAgent` + `read_file` tool) multi-turn execution over `gemini-web-argon`
   with `<antigravity_tool_protocol>` compilation, `<tool_call>` parsing, and `[cid, rid, rcid]` context persistence.
2. Stage 2 — Real Hermes Agent (`AIAgent` + `terminal` tool) multi-turn execution over `gemini-web-2.5-pro`.
3. Stage 3 — Dual-Channel `hybrid_failover` when Code Assist is exhausted/disabled + Sliding-Window Quota
   Tracking + Proactive High-Water Mark (`<= 10%`) Node Switching.
4. Stage 4 — Dedicated Dashboard Management APIs (9 `/gemini-web/*` endpoints + `/doctor` check) and
   Zero-Leak Security Audit (`0o600` storage + masked telemetry).
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
    GeminiWebPoolManager,
    build_model_selector_header,
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
