"""BardFrontendService/StreamGenerate Client for Gemini Web App (`gemini.google.com/app`).

Implements:
- Zero-browser `httpx.AsyncClient` communication with `BardFrontendService/StreamGenerate`.
- Model selection via `x-goog-ext-525001261-jspb` header (`Gemini Argon`, `2.5 Pro`, `2.5 Flash`).
- Self-healing CSRF (`SNlM0e`) refresh and automatic fallback to `gemini-web-default` if Google rotates model hex IDs.
- Server-side conversation state (`[cid, rid, rcid]`) persistence across multi-turn Hermes tool calls.
- Full OpenAI ChatCompletions (non-streaming and SSE streaming) + Hermes Tool-Calling via `GeminiWebToolAdapter`.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.parse
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Set

import httpx

from .models import build_model_selector_header, resolve_gemini_web_model
from .pool_manager import GeminiWebNode, GeminiWebPoolManager
from .session_manager import DEFAULT_USER_AGENT, GeminiWebSessionManager
from .tool_adapter import GeminiWebToolAdapter

logger = logging.getLogger(__name__)

STREAM_GENERATE_ENDPOINT = (
    "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
)


def parse_bard_stream_generate_response(raw_body: str) -> Dict[str, Any]:
    """Parse Google's `)]}'` chunked RPC framing from `BardFrontendService/StreamGenerate`.

    Returns:
        {
            "ok": bool,
            "text": str,
            "thoughts": str,
            "cid": str,
            "rid": str,
            "rcid": str,
            "images": List[str],
            "error": Optional[str],
            "error_code": Optional[int],
        }
    """
    result: Dict[str, Any] = {
        "ok": False,
        "text": "",
        "thoughts": "",
        "cid": "",
        "rid": "",
        "rcid": "",
        "images": [],
        "error": None,
        "error_code": None,
    }
    if not raw_body:
        result["error"] = "Empty response body from BardFrontendService."
        return result

    cleaned = raw_body.strip()
    if cleaned.startswith(")]}'"):
        cleaned = cleaned[4:].strip()

    # Collect all JSON array lines inside the response
    best_text = ""
    best_thoughts = ""
    cid = ""
    rid = ""
    rcid = ""
    images: List[str] = []
    rpc_error_code: Optional[int] = None

    for line in cleaned.splitlines():
        line_str = line.strip()
        if not line_str or line_str.isdigit():
            continue
        if not line_str.startswith("["):
            continue
        try:
            outer = json.loads(line_str)
        except Exception:
            continue
        if not isinstance(outer, list):
            continue

        for item in outer:
            if not isinstance(item, list) or len(item) < 3:
                continue
            if item[0] != "wrb.fr":
                continue

            inner_str = item[2]
            if inner_str is None:
                # Check if an error code exists at index 5
                if len(item) > 5 and isinstance(item[5], list) and item[5]:
                    try:
                        rpc_error_code = int(item[5][0])
                    except Exception:
                        pass
                continue

            if not isinstance(inner_str, str):
                continue

            try:
                body = json.loads(inner_str)
            except Exception:
                continue

            if not isinstance(body, list):
                continue

            # Extract [cid, rid] at body[1]
            if len(body) > 1 and isinstance(body[1], list) and len(body[1]) >= 2:
                if body[1][0]:
                    cid = str(body[1][0])
                if body[1][1]:
                    rid = str(body[1][1])

            # Extract candidate list at body[4]
            if len(body) > 4 and isinstance(body[4], list) and len(body[4]) > 0:
                candidate = body[4][0]
                if isinstance(candidate, list):
                    if len(candidate) > 0 and candidate[0]:
                        rcid = str(candidate[0])
                    if (
                        len(candidate) > 1
                        and isinstance(candidate[1], list)
                        and len(candidate[1]) > 0
                        and isinstance(candidate[1][0], str)
                    ):
                        candidate_text = candidate[1][0]
                        if len(candidate_text) >= len(best_text):
                            best_text = candidate_text
                    # Thoughts / Reasoning trace (often in candidate[37] or candidate[2])
                    if len(candidate) > 37 and isinstance(candidate[37], list):
                        try:
                            thought_candidate = candidate[37][0][0]
                            if isinstance(thought_candidate, str) and len(thought_candidate) >= len(best_thoughts):
                                best_thoughts = thought_candidate
                        except Exception:
                            pass
                    elif len(candidate) > 2 and isinstance(candidate[2], str) and candidate[2].strip():
                        best_thoughts = candidate[2].strip()

                    # Generated images if any
                    if len(candidate) > 12 and isinstance(candidate[12], list):
                        try:
                            img_entries = candidate[12][7][0]
                            if isinstance(img_entries, list):
                                for img_entry in img_entries:
                                    if isinstance(img_entry, list) and img_entry and isinstance(img_entry[0], list):
                                        img_url = img_entry[0][0]
                                        if isinstance(img_url, str) and img_url.startswith("http"):
                                            images.append(img_url)
                        except Exception:
                            pass

    if best_text:
        result["ok"] = True
        result["text"] = best_text
        result["thoughts"] = best_thoughts
        result["cid"] = cid
        result["rid"] = rid
        result["rcid"] = rcid
        result["images"] = images
        return result

    result["error_code"] = rpc_error_code
    result["error"] = (
        f"BardFrontendService returned no candidate text (rpc_error_code={rpc_error_code})."
    )
    return result


class GeminiWebClient:
    """Executes inference requests against `gemini.google.com/app` managed by `GeminiWebPoolManager`."""

    def __init__(
        self,
        pool_manager: Optional[GeminiWebPoolManager] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.pool = pool_manager or GeminiWebPoolManager()
        self.session_manager: GeminiWebSessionManager = self.pool.session_manager
        self._external_http = http_client

    def _build_f_req_payload(
        self,
        prompt_text: str,
        conversation_ctx: Optional[List[str]] = None,
        lang: str = "vi",
    ) -> str:
        ctx = conversation_ctx if (conversation_ctx and len(conversation_ctx) == 3) else ["", "", ""]
        inner = [
            [prompt_text, 0, None, [], None, None, 0],
            [lang],
            [ctx[0], ctx[1], ctx[2], None, None, []],
        ]
        inner_json = json.dumps(inner, ensure_ascii=False, separators=(",", ":"))
        outer_json = json.dumps([None, inner_json], ensure_ascii=False, separators=(",", ":"))
        return outer_json

    async def generate_on_node(
        self,
        node: GeminiWebNode,
        prompt_text: str,
        model_name: str = "gemini-web-argon",
        conversation_ctx: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Send a single `StreamGenerate` RPC request using a specific `GeminiWebNode`."""
        close_client = False
        http = self._external_http
        if http is None:
            http = httpx.AsyncClient(timeout=90.0, follow_redirects=True)
            close_client = True

        try:
            sess = await self.session_manager.ensure_fresh_cookie(node.node_id, http_client=http)
            if not sess:
                return {"ok": False, "error": f"No cookie session found for node '{node.node_id}'."}

            snlm0e = str(sess.get("snlm0e") or "")
            cfb2h = str(sess.get("cfb2h") or "boq_assistant-bard-web-server_20260501.08_p0")
            fsid = str(sess.get("fsid") or "")

            if not snlm0e:
                probe = await self.session_manager.handshake_and_probe_models(node.node_id, http_client=http)
                if not probe.get("ok"):
                    return {
                        "ok": False,
                        "error": probe.get("error") or "Failed to obtain SNlM0e token.",
                    }
                sess = self.session_manager.get_session(node.node_id) or sess
                snlm0e = str(sess.get("snlm0e") or "")
                cfb2h = str(sess.get("cfb2h") or cfb2h)
                fsid = str(sess.get("fsid") or fsid)

            if snlm0e.startswith("oauth_bridge:"):
                return await self._generate_via_linked_oauth_account(
                    node=node,
                    prompt_text=prompt_text,
                    model_name=model_name,
                    http=http,
                )

            cookies = dict(sess.get("cookies") or {})
            user_agent = str(sess.get("user_agent") or DEFAULT_USER_AGENT)
            model_header_val = build_model_selector_header(
                model_name,
                node_available_models=node.available_models,
            )

            async def _do_post(cur_snlm0e: str, cur_cfb2h: str, cur_fsid: str, cur_model_hdr: Optional[str]) -> httpx.Response:
                req_id = random.randint(100000, 999999)
                query_params = {
                    "bl": cur_cfb2h,
                    "hl": "vi",
                    "_reqid": str(req_id),
                    "rt": "c",
                }
                if cur_fsid:
                    query_params["f.sid"] = cur_fsid

                url = f"{STREAM_GENERATE_ENDPOINT}?{urllib.parse.urlencode(query_params)}"
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "Origin": "https://gemini.google.com",
                    "Referer": "https://gemini.google.com/app",
                    "User-Agent": user_agent,
                    "X-Same-Domain": "1",
                }
                if cur_model_hdr:
                    headers["x-goog-ext-525001261-jspb"] = cur_model_hdr

                form_body = urllib.parse.urlencode(
                    {
                        "f.req": self._build_f_req_payload(prompt_text, conversation_ctx),
                        "at": cur_snlm0e,
                    }
                )
                return await http.post(url, content=form_body, headers=headers, cookies=cookies)

            resp = await _do_post(snlm0e, cfb2h, fsid, model_header_val)
            parsed = parse_bard_stream_generate_response(resp.text if resp.status_code == 200 else "")

            # Self-healing retry: if SNlM0e expired or custom model hex was rejected, re-handshake and fallback
            if not parsed.get("ok"):
                logger.info(
                    "Node '%s' returned empty/error on first attempt (%s); refreshing SNlM0e & retrying with self-healing fallback...",
                    node.node_id,
                    parsed.get("error"),
                )
                probe = await self.session_manager.handshake_and_probe_models(node.node_id, http_client=http)
                if probe.get("ok"):
                    sess = self.session_manager.get_session(node.node_id) or sess
                    new_snlm0e = str(sess.get("snlm0e") or snlm0e)
                    if new_snlm0e.startswith("oauth_bridge:"):
                        return await self._generate_via_linked_oauth_account(
                            node=node,
                            prompt_text=prompt_text,
                            model_name=model_name,
                            http=http,
                        )
                    cookies = dict(sess.get("cookies") or {})
                    resp2 = await _do_post(
                        new_snlm0e,
                        str(sess.get("cfb2h") or cfb2h),
                        str(sess.get("fsid") or fsid),
                        None,  # Fallback to UI default model if custom hex header caused failure
                    )
                    if resp2.status_code == 200:
                        parsed = parse_bard_stream_generate_response(resp2.text)

            if not parsed.get("ok") and (node.email or node.linked_oauth_account_id):
                fallback_res = await self._generate_via_linked_oauth_account(
                    node=node,
                    prompt_text=prompt_text,
                    model_name=model_name,
                    http=http,
                )
                if fallback_res.get("ok"):
                    return fallback_res

            return parsed
        except Exception as e:
            logger.warning("GeminiWebClient.generate_on_node error on %s: %s", node.node_id, e)
            return {"ok": False, "error": str(e)}
        finally:
            if close_client:
                await http.aclose()

    async def _generate_via_linked_oauth_account(
        self,
        node: GeminiWebNode,
        prompt_text: str,
        model_name: str,
        http: httpx.AsyncClient,
    ) -> Dict[str, Any]:
        """Execute Gemini inference using the node's linked Google OAuth account when running in OAuth-Bridge mode."""
        try:
            try:
                from tools.antigravity_bridge.auth import AntigravityAuthManager
                from tools.antigravity_bridge.client import (
                    CODE_ASSIST_BASE_URL,
                    DEFAULT_PROJECT_ID,
                    FALLBACK_CODE_ASSIST_BASE_URL,
                    build_antigravity_headers,
                )
            except ImportError:
                from ..auth import AntigravityAuthManager
                from ..client import (
                    CODE_ASSIST_BASE_URL,
                    DEFAULT_PROJECT_ID,
                    FALLBACK_CODE_ASSIST_BASE_URL,
                    build_antigravity_headers,
                )

            auth_file = self.session_manager.hermes_dir / "auth" / "antigravity_tokens.json"
            if not auth_file.is_file():
                alt_file = self.session_manager.hermes_dir / "antigravity_tokens.json"
                if alt_file.is_file():
                    auth_file = alt_file

            auth_mgr = AntigravityAuthManager(auth_file=auth_file) if auth_file.is_file() else AntigravityAuthManager()
            target_email = (node.email or node.linked_oauth_account_id or "").strip()
            creds = auth_mgr.resolve_valid_credentials(bearer_token=target_email)
            if not creds:
                creds = auth_mgr.resolve_valid_credentials(bearer_token="")
            if not creds:
                return {"ok": False, "error": f"No valid OAuth credentials found for linked node '{node.email}'."}

            effective_proj = (
                getattr(creds, "effective_project_id", None)
                or getattr(creds, "project_id", None)
                or DEFAULT_PROJECT_ID
            )
            upstream_model = "gemini-2.5-flash" if "flash" in (model_name or "").lower() else "gemini-2.5-pro"
            prompt_id = str(uuid.uuid4())
            envelope = {
                "model": upstream_model,
                "project": effective_proj,
                "user_prompt_id": prompt_id,
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
                    "generationConfig": {"temperature": 0.4},
                },
            }
            headers = build_antigravity_headers(
                creds.access_token,
                effective_proj,
                prompt_id=prompt_id,
                trajectory_id=str(uuid.uuid4()),
            )
            resp = await http.post(f"{CODE_ASSIST_BASE_URL}:generateContent", json=envelope, headers=headers)
            if resp.status_code in {404, 429, 500, 502, 503, 504}:
                resp = await http.post(f"{FALLBACK_CODE_ASSIST_BASE_URL}:generateContent", json=envelope, headers=headers)

            if resp.status_code != 200:
                return {"ok": False, "error": f"Linked Google account returned HTTP {resp.status_code}"}

            data = resp.json()
            inner = data.get("response") if isinstance(data.get("response"), dict) else data
            candidates = inner.get("candidates") or []
            text_out = ""
            thoughts_out = ""
            if candidates and isinstance(candidates[0], dict):
                parts = (candidates[0].get("content") or {}).get("parts") or []
                for p in parts:
                    if not isinstance(p, dict):
                        continue
                    if p.get("thought") is True and isinstance(p.get("text"), str):
                        thoughts_out += p["text"]
                    elif isinstance(p.get("text"), str):
                        text_out += p["text"]

            if not text_out and thoughts_out:
                text_out = thoughts_out

            if not text_out:
                return {"ok": False, "error": "Empty candidate text from linked Google account."}

            return {
                "ok": True,
                "text": text_out,
                "thoughts": thoughts_out,
                "cid": f"c_{node.node_id[:10]}",
                "rid": f"r_{int(time.time())}",
                "rcid": f"rc_{int(time.time())}",
                "images": [],
                "error": None,
                "error_code": None,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def create_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        preferred_node_id: str = "",
    ) -> Dict[str, Any]:
        """Execute a complete OpenAI-compatible ChatCompletion (with Hermes Tool-Calling) over Gemini Web."""
        requested_model = str(openai_payload.get("model") or "gemini-web-argon")
        canonical_model = resolve_gemini_web_model(requested_model)
        session_key = self.pool.compute_session_key(openai_payload)

        excluded_nodes: Set[str] = set()
        all_nodes = self.pool.list_nodes()
        max_attempts = max(1, len(all_nodes))
        last_error = "No ready Gemini Web App nodes in pool."

        for attempt in range(max_attempts):
            if attempt == 0 and preferred_node_id:
                node = self.pool.get_node(preferred_node_id)
            else:
                node = self.pool.select_node_for_model(
                    canonical_model,
                    session_key=session_key,
                    exclude_node_ids=excluded_nodes,
                )

            if not node:
                break

            excluded_nodes.add(node.node_id)
            conv_ctx = self.pool.get_conversation_context(session_key, node.node_id)
            prompt_text, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(
                openai_payload,
                incremental_only=bool(conv_ctx),
            )

            gen_res = await self.generate_on_node(
                node=node,
                prompt_text=prompt_text,
                model_name=canonical_model,
                conversation_ctx=conv_ctx,
            )

            if gen_res.get("ok"):
                self.pool.record_web_usage(node.node_id, canonical_model, success=True)
                if gen_res.get("cid"):
                    self.pool.save_conversation_context(
                        session_key=session_key,
                        node_id=node.node_id,
                        cid=str(gen_res.get("cid") or ""),
                        rid=str(gen_res.get("rid") or ""),
                        rcid=str(gen_res.get("rcid") or ""),
                    )

                completion = GeminiWebToolAdapter.build_openai_chat_completion(
                    raw_text=str(gen_res.get("text") or ""),
                    model=requested_model,
                    thoughts_text=str(gen_res.get("thoughts") or ""),
                    prompt_text=prompt_text,
                )
                completion["x_gemini_web_node"] = node.node_id
                completion["x_gemini_web_model"] = canonical_model
                return completion

            err_str = str(gen_res.get("error") or "Unknown BardFrontendService failure")
            last_error = err_str
            self.pool.record_web_usage(node.node_id, canonical_model, success=False, error_msg=err_str)
            self.pool.mark_web_model_cooldown(
                node.node_id,
                canonical_model,
                cooldown_seconds=900.0,
                reason=err_str,
            )
            logger.warning(
                "Gemini Web node '%s' failed on model '%s' (%s), failing over to next web node...",
                node.node_id,
                canonical_model,
                err_str,
            )

        raise RuntimeError(f"Gemini Web App pool exhausted or failed: {last_error}")

    async def stream_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        preferred_node_id: str = "",
    ) -> AsyncIterator[str]:
        """Stream OpenAI-compatible SSE chunks (`chat.completion.chunk`) from Gemini Web."""
        completion = await self.create_chat_completion(
            openai_payload,
            preferred_node_id=preferred_node_id,
        )
        stream_id = completion.get("id") or f"chatcmpl-gweb-{uuid.uuid4().hex[:20]}"
        created = completion.get("created") or int(time.time())
        model = completion.get("model") or "gemini-web-argon"
        choice = (completion.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        finish_reason = choice.get("finish_reason") or "stop"

        # 1. Initial assistant role chunk
        init_chunk = {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(init_chunk, ensure_ascii=False)}\n\n"

        # 2. Reasoning trace chunk if present
        reasoning = msg.get("reasoning_content")
        if reasoning:
            r_chunk = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": reasoning, "reasoning": reasoning},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(r_chunk, ensure_ascii=False)}\n\n"

        # 3. Content chunk if present
        content = msg.get("content")
        if content:
            c_chunk = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(c_chunk, ensure_ascii=False)}\n\n"

        # 4. Tool calls chunk if present
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            delta_tcs = []
            for idx, tc in enumerate(tool_calls):
                tc_copy = dict(tc)
                tc_copy["index"] = idx
                delta_tcs.append(tc_copy)
            tc_chunk = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"tool_calls": delta_tcs}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(tc_chunk, ensure_ascii=False)}\n\n"

        # 5. Final finish_reason chunk + [DONE]
        final_chunk = {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
