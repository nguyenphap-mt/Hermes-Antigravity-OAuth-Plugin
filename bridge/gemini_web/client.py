"""BardFrontendService/StreamGenerate Client for Gemini Web App (`gemini.google.com/app`).

Implements:
- Zero-browser `httpx.AsyncClient` communication with `BardFrontendService/StreamGenerate`.
- Model selection via `x-goog-ext-525001261-jspb` header (`Gemini Argon`, `2.5 Pro`, `2.5 Flash`).
- Self-healing CSRF (`SNlM0e`) refresh and automatic fallback to `gemini-web-default` if Google rotates model hex IDs.
- Server-side conversation state (`[cid, rid, rcid]`) persistence across multi-turn Hermes tool calls.
- Full OpenAI ChatCompletions (non-streaming and SSE streaming) + Hermes Tool-Calling via `GeminiWebToolAdapter`.
"""

from __future__ import annotations

import datetime
import json
import logging
import random
import re
import time
import urllib.parse
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

import httpx

from .models import build_model_selector_header, resolve_gemini_web_model
from .pool_manager import GeminiWebNode, GeminiWebPoolManager
from .session_manager import (
    DEFAULT_USER_AGENT,
    GeminiWebSessionManager,
    is_synthetic_oauth_cookie,
)
from .tool_adapter import GeminiWebToolAdapter

logger = logging.getLogger(__name__)

STREAM_GENERATE_ENDPOINT = (
    "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
)


def parse_gemini_web_quota_exhaustion(
    raw_body: str,
    candidate_text: str = "",
    rpc_error_code: Optional[int] = None,
    now_ts: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Detect Gemini Web quota exhaustion banners (e.g. 'Đã đạt đến hạn mức · Đặt lại lúc 21:07') and compute cooldown."""
    cand_clean = (candidate_text or "").strip()
    cand_low = cand_clean.lower()
    raw_low = (raw_body or "").lower()

    quota_markers = (
        "đã đạt đến hạn mức",
        "đặt lại lúc",
        "vượt quá hạn mức",
        "you've reached your limit",
        "reached your limit",
        "resets at",
    )

    is_cand_quota = bool(cand_clean and len(cand_clean) <= 360 and any(m in cand_low for m in quota_markers))
    is_raw_quota = bool(not cand_clean and any(m in raw_low for m in quota_markers))
    is_rpc_quota = bool(not cand_clean and rpc_error_code in {8, 429, 1013})

    if not (is_cand_quota or is_raw_quota or is_rpc_quota):
        return None

    scan_text = cand_clean if is_cand_quota else (raw_body or "")
    time_match = re.search(
        r"(?:đặt lại lúc|resets at|try again at|lúc)\s*(\d{1,2}):(\d{2})(?:\s*(am|pm))?",
        scan_text,
        flags=re.IGNORECASE,
    )
    if not time_match:
        time_match = re.search(r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b", scan_text, flags=re.IGNORECASE)

    cur_ts = now_ts if now_ts is not None else time.time()
    tz_vn = datetime.timezone(datetime.timedelta(hours=7))
    reset_time_label = ""
    cooldown_seconds = 3600.0

    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        ampm = (time_match.group(3) or "").strip().lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            reset_time_label = f"{hour:02d}:{minute:02d}"
            now_dt = datetime.datetime.fromtimestamp(cur_ts, tz=tz_vn)
            target_dt = now_dt.replace(hour=hour, minute=minute, second=5, microsecond=0)
            if target_dt <= now_dt:
                target_dt += datetime.timedelta(days=1)
            cooldown_seconds = max(300.0, float((target_dt - now_dt).total_seconds()))

    reason = (
        cand_clean
        if is_cand_quota
        else (
            f"Đã đạt đến hạn mức · Đặt lại lúc {reset_time_label}"
            if reset_time_label
            else f"Đã đạt đến hạn mức trên gemini.google.com (rpc_error_code={rpc_error_code})"
        )
    )
    return {
        "exhausted": True,
        "reset_time_label": reset_time_label,
        "cooldown_seconds": cooldown_seconds,
        "reason": reason,
    }


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
                    cand_rcid = str(candidate[0]) if (len(candidate) > 0 and candidate[0]) else ""
                    if (
                        len(candidate) > 1
                        and isinstance(candidate[1], list)
                        and len(candidate[1]) > 0
                        and isinstance(candidate[1][0], str)
                    ):
                        candidate_text = candidate[1][0]
                        if candidate_text and len(candidate_text) >= len(best_text):
                            best_text = candidate_text
                            if cand_rcid:
                                rcid = cand_rcid
                    if cand_rcid and not rcid:
                        rcid = cand_rcid
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

    quota_info = parse_gemini_web_quota_exhaustion(
        raw_body=raw_body,
        candidate_text=best_text,
        rpc_error_code=rpc_error_code,
    )
    if quota_info:
        result["ok"] = False
        result["quota_exhausted"] = True
        result["reset_time_label"] = quota_info["reset_time_label"]
        result["cooldown_seconds"] = quota_info["cooldown_seconds"]
        result["error_code"] = rpc_error_code or 429
        result["error"] = quota_info["reason"]
        return result

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
        full_prompt_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a single `StreamGenerate` RPC request using a specific `GeminiWebNode`."""
        effective_full_prompt = full_prompt_text or prompt_text
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

            if not snlm0e or is_synthetic_oauth_cookie(snlm0e):
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

            cookies = dict(sess.get("cookies") or {})
            user_agent = str(sess.get("user_agent") or DEFAULT_USER_AGENT)
            model_header_val = build_model_selector_header(
                model_name,
                node_available_models=node.available_models,
            )

            async def _do_post(
                cur_snlm0e: str,
                cur_cfb2h: str,
                cur_fsid: str,
                cur_model_hdr: Optional[str],
                cur_prompt: str = prompt_text,
                cur_ctx: Optional[List[str]] = conversation_ctx,
            ) -> httpx.Response:
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
                        "f.req": self._build_f_req_payload(cur_prompt, cur_ctx),
                        "at": cur_snlm0e,
                    }
                )
                return await http.post(url, content=form_body, headers=headers, cookies=cookies)

            resp = await _do_post(snlm0e, cfb2h, fsid, model_header_val)
            parsed = parse_bard_stream_generate_response(resp.text if resp.status_code == 200 else "")
            if parsed.get("quota_exhausted"):
                return parsed

            # Self-healing retry: if SNlM0e expired or custom model hex / stale cid was rejected, re-handshake and fallback
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
                    cookies = dict(sess.get("cookies") or {})
                    resp2 = await _do_post(
                        new_snlm0e,
                        str(sess.get("cfb2h") or cfb2h),
                        str(sess.get("fsid") or fsid),
                        None,  # Fallback to UI default model if custom hex header caused failure
                        cur_prompt=effective_full_prompt,
                        cur_ctx=None,
                    )
                    if resp2.status_code == 200:
                        parsed = parse_bard_stream_generate_response(resp2.text)

            return parsed
        except Exception as e:
            logger.warning("GeminiWebClient.generate_on_node error on %s: %s", node.node_id, e)
            return {"ok": False, "error": str(e)}
        finally:
            if close_client:
                await http.aclose()

    async def create_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        preferred_node_id: str = "",
    ) -> Dict[str, Any]:
        """Execute a complete OpenAI-compatible ChatCompletion (with Hermes Tool-Calling) over Gemini Web."""
        requested_model = str(openai_payload.get("model") or "gemini-web-argon")
        canonical_model = resolve_gemini_web_model(requested_model)
        session_key = self.pool.compute_session_key(openai_payload)
        messages: List[Dict[str, Any]] = list(openai_payload.get("messages") or [])
        expected_history_hash = self.pool.compute_history_hash(messages, include_trailing=False)
        full_prompt_text, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(
            openai_payload,
            incremental_only=False,
        )

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
            conv_ctx = self.pool.get_conversation_context(
                session_key,
                node.node_id,
                expected_history_hash=expected_history_hash,
            )
            if conv_ctx:
                prompt_text, _ = GeminiWebToolAdapter.compile_openai_to_web_prompt(
                    openai_payload,
                    incremental_only=True,
                )
            else:
                prompt_text = full_prompt_text

            gen_res = await self.generate_on_node(
                node=node,
                prompt_text=prompt_text,
                full_prompt_text=full_prompt_text,
                model_name=canonical_model,
                conversation_ctx=conv_ctx,
            )

            if gen_res.get("ok"):
                self.pool.record_web_usage(node.node_id, canonical_model, success=True)
                completion = GeminiWebToolAdapter.build_openai_chat_completion(
                    raw_text=str(gen_res.get("text") or ""),
                    model=requested_model,
                    thoughts_text=str(gen_res.get("thoughts") or ""),
                    prompt_text=prompt_text,
                )
                if gen_res.get("cid") and gen_res.get("is_stateful", True) is not False:
                    assistant_msg = ((completion.get("choices") or [{}])[0]).get("message") or {
                        "role": "assistant",
                        "content": str(gen_res.get("text") or ""),
                    }
                    new_history_hash = self.pool.compute_history_hash(
                        messages + [assistant_msg],
                        include_trailing=True,
                    )
                    self.pool.save_conversation_context(
                        session_key=session_key,
                        node_id=node.node_id,
                        cid=str(gen_res.get("cid") or ""),
                        rid=str(gen_res.get("rid") or ""),
                        rcid=str(gen_res.get("rcid") or ""),
                        history_hash=new_history_hash,
                    )
                else:
                    self.pool.invalidate_conversation_context(session_key, node.node_id)

                completion["x_gemini_web_node"] = node.node_id
                completion["x_gemini_web_model"] = canonical_model
                return completion

            err_str = str(gen_res.get("error") or "Unknown BardFrontendService failure")
            last_error = err_str
            cooldown_sec = float(gen_res.get("cooldown_seconds") or 900.0)
            self.pool.record_web_usage(node.node_id, canonical_model, success=False, error_msg=err_str)
            self.pool.mark_web_model_cooldown(
                node.node_id,
                canonical_model,
                cooldown_seconds=cooldown_sec,
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
