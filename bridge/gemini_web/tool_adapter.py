"""Bidirectional OpenAI Tool-Calling <-> Gemini Web XML/JSON Protocol Adapter.

Enables Hermes Agent (`AIAgent` in `run_agent.py`) to execute multi-turn tool calls
(`terminal`, `read_file`, `write_file`, `search_files`, `web_search`, etc.) seamlessly
over `gemini.google.com/app` (`BardFrontendService/StreamGenerate`), which only accepts
a text prompt envelope rather than native OpenAI `tools` JSON schemas.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TOOL_CALL_TAG_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)

_TOOL_CALL_FENCE_RE = re.compile(
    r"```(?:tool_call|xml|json)\s*(?:<tool_call>)?\s*(\{.*?\})\s*(?:</tool_call>)?\s*```",
    re.DOTALL | re.IGNORECASE,
)


def _coerce_text(content: Any) -> str:
    """Convert OpenAI message content (str, list of parts, or None) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(content)


def _compact_tool_definitions(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a compact, token-efficient tool specification array for the prompt envelope."""
    compact: List[Dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") if t.get("type") == "function" else t
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name:
            continue
        params = fn.get("parameters") or {}
        props = params.get("properties") if isinstance(params, dict) else {}
        req = params.get("required") if isinstance(params, dict) else []
        compact_props: Dict[str, Any] = {}
        if isinstance(props, dict):
            for k, v in props.items():
                if isinstance(v, dict):
                    compact_props[k] = {
                        "type": v.get("type", "string"),
                        "description": str(v.get("description", ""))[:180],
                    }
                    if "enum" in v:
                        compact_props[k]["enum"] = v["enum"]
                else:
                    compact_props[k] = {"type": "string"}
        compact.append(
            {
                "name": name,
                "description": str(fn.get("description", ""))[:260],
                "parameters": {
                    "type": "object",
                    "properties": compact_props,
                    "required": req if isinstance(req, list) else [],
                },
            }
        )
    return compact


class GeminiWebToolAdapter:
    """Compiles OpenAI chat/tool payloads into Gemini Web prompts and parses `<tool_call>` responses."""

    @staticmethod
    def compile_openai_to_web_prompt(
        openai_payload: Dict[str, Any],
        incremental_only: bool = False,
    ) -> Tuple[str, bool]:
        """Compile an OpenAI ChatCompletion payload into a structured prompt for BardFrontendService.

        Returns:
            (prompt_text, has_tools)
        """
        messages: List[Dict[str, Any]] = list(openai_payload.get("messages") or [])
        raw_tools: List[Dict[str, Any]] = list(openai_payload.get("tools") or [])
        if not raw_tools and openai_payload.get("functions"):
            raw_tools = [{"type": "function", "function": f} for f in openai_payload["functions"]]

        has_tools = len(raw_tools) > 0
        tool_choice = openai_payload.get("tool_choice")
        if tool_choice == "none":
            has_tools = False

        # Build tool_call_id -> tool_name lookup map from all assistant tool_calls
        tool_id_to_name: Dict[str, str] = {}
        for msg in messages:
            if isinstance(msg, dict) and str(msg.get("role") or "").lower() == "assistant":
                for tc in msg.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        tc_id = str(tc.get("id") or "").strip()
                        fn = tc.get("function") or {}
                        fn_name = str(fn.get("name") or "").strip()
                        if tc_id and fn_name:
                            tool_id_to_name[tc_id] = fn_name

        # When continuing an existing server-side conversation ([cid, rid, rcid]) and there is at least
        # one prior assistant turn, send all new messages after the last assistant turn.
        if incremental_only and messages:
            last_assistant_idx = -1
            for idx in range(len(messages) - 1, -1, -1):
                if isinstance(messages[idx], dict) and str(messages[idx].get("role") or "").lower() == "assistant":
                    last_assistant_idx = idx
                    break
            if last_assistant_idx >= 0 and last_assistant_idx + 1 < len(messages):
                trailing_Slice = messages[last_assistant_idx + 1 :]
                inc_lines: List[str] = []
                has_tool_resp = False
                for m in trailing_Slice:
                    r = str(m.get("role") or "").lower()
                    if r in ("tool", "function"):
                        has_tool_resp = True
                        t_id = str(m.get("tool_call_id") or "")
                        t_name = str(m.get("name") or tool_id_to_name.get(t_id) or t_id or "tool")
                        inc_lines.append(
                            f'<tool_response id="{t_id}" name="{t_name}">\n{_coerce_text(m.get("content"))}\n</tool_response>'
                        )
                    else:
                        inc_lines.append(_coerce_text(m.get("content")))
                if has_tools:
                    if has_tool_resp:
                        inc_lines.append(
                            "\n[INSTRUCTION]: Continue assisting the user based on the tool response(s) above. "
                            "If you need to invoke another tool, output ONLY the exact <tool_call>{...}</tool_call> XML block. "
                            "Otherwise, provide your final response directly."
                        )
                    else:
                        inc_lines.append(
                            "\n[INSTRUCTION]: If you need to invoke a tool to fulfill this request, "
                            "output ONLY the exact <tool_call>{...}</tool_call> XML block. "
                            "Otherwise, respond directly to the user."
                        )
                return "\n\n".join(inc_lines).strip(), has_tools

        sections: List[str] = []

        # 1. Inject Tool Protocol & Schema if tools are enabled
        if has_tools:
            compact_tools = _compact_tool_definitions(raw_tools)
            tools_json = json.dumps(compact_tools, ensure_ascii=False, indent=2)
            sections.append(
                "<antigravity_tool_protocol>\n"
                "You have access to external tools executed by the Hermes Agent runtime.\n"
                "AVAILABLE TOOLS SCHEMA:\n"
                f"{tools_json}\n\n"
                "CRITICAL TOOL CALLING RULES:\n"
                "1. When you need to call a tool to fulfill the request, output ONE OR MORE `<tool_call>` XML blocks in this EXACT format:\n"
                "<tool_call>\n"
                '{"name": "tool_name_here", "arguments": {"param1": "value1"}}\n'
                "</tool_call>\n"
                "2. Do NOT fabricate or guess tool outputs. Stop immediately after outputting `<tool_call>...</tool_call>` and wait for `<tool_response>`.\n"
                "3. When `<tool_response>` is already provided in the conversation history and no further tool calls are needed, answer the user directly without `<tool_call>` tags.\n"
                "</antigravity_tool_protocol>"
            )

        # 2. Compile Conversation History preserving strict role semantics
        transcript_blocks: List[str] = []
        for msg in messages:
            role = str(msg.get("role") or "user").lower()
            text = _coerce_text(msg.get("content"))
            tool_calls = msg.get("tool_calls") or []

            if role == "system" or role == "developer":
                if text.strip():
                    transcript_blocks.append(f"[SYSTEM_INSTRUCTION]\n{text.strip()}\n[/SYSTEM_INSTRUCTION]")
            elif role == "user":
                transcript_blocks.append(f"[USER]\n{text.strip()}\n[/USER]")
            elif role == "assistant":
                parts_str: List[str] = []
                reasoning = str(msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
                if reasoning:
                    parts_str.append(f"<thinking>\n{reasoning}\n</thinking>")
                if text.strip():
                    parts_str.append(text.strip())
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = str(tc.get("id") or "")
                        fn = tc.get("function") or {}
                        tc_name = fn.get("name") or ""
                        tc_args_raw = fn.get("arguments") or "{}"
                        try:
                            tc_args = json.loads(tc_args_raw) if isinstance(tc_args_raw, str) else tc_args_raw
                        except Exception:
                            tc_args = {"raw": str(tc_args_raw)}
                        tc_payload: Dict[str, Any] = {"name": tc_name, "arguments": tc_args}
                        if tc_id:
                            tc_payload = {"id": tc_id, "name": tc_name, "arguments": tc_args}
                        tc_json = json.dumps(tc_payload, ensure_ascii=False)
                        parts_str.append(f"<tool_call>\n{tc_json}\n</tool_call>")
                joined_assistant = "\n".join(parts_str)
                transcript_blocks.append(f"[ASSISTANT]\n{joined_assistant}\n[/ASSISTANT]")
            elif role in ("tool", "function"):
                t_id = str(msg.get("tool_call_id") or "")
                t_name = str(msg.get("name") or tool_id_to_name.get(t_id) or t_id or "tool")
                transcript_blocks.append(
                    f'[TOOL_RESPONSE id="{t_id}" name="{t_name}"]\n{text.strip()}\n[/TOOL_RESPONSE]'
                )

        # Optimization: If there is only a single user message and no tools/system messages, send raw text cleanly
        if (
            not has_tools
            and len(messages) == 1
            and str(messages[0].get("role") or "user") == "user"
        ):
            return _coerce_text(messages[0].get("content")).strip(), False

        sections.append("\n\n".join(transcript_blocks))
        if has_tools:
            sections.append(
                "Respond as [ASSISTANT]. If a tool call is required next, emit `<tool_call>{\"name\": ..., \"arguments\": ...}</tool_call>`."
            )
        else:
            sections.append("Respond directly to the latest [USER] request above without wrapping your response in [ASSISTANT] tags.")

        return "\n\n".join(s for s in sections if s).strip(), has_tools

    @staticmethod
    def extract_tool_calls_and_clean_text(
        raw_text: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Parse `<tool_call>` blocks from Gemini Web response text into OpenAI `tool_calls` array."""
        if not raw_text:
            return [], ""

        extracted_calls: List[Dict[str, Any]] = []
        cleaned_text = raw_text

        def _try_parse_json_candidate(json_str: str) -> Optional[Dict[str, Any]]:
            candidate = json_str.strip()
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and obj.get("name"):
                    return obj
            except Exception:
                # Repair common trailing commas or smart quotes
                repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    obj = json.loads(repaired)
                    if isinstance(obj, dict) and obj.get("name"):
                        return obj
                except Exception:
                    pass
            return None

        # 1. Match explicit <tool_call>...</tool_call> tags
        matches = list(_TOOL_CALL_TAG_RE.finditer(raw_text))
        if not matches:
            matches = list(_TOOL_CALL_FENCE_RE.finditer(raw_text))

        for m in matches:
            parsed = _try_parse_json_candidate(m.group(1))
            if not parsed:
                continue
            fn_name = str(parsed.get("name")).strip()
            fn_args = parsed.get("arguments")
            if fn_args is None:
                fn_args = parsed.get("parameters") or {}
            if isinstance(fn_args, str):
                try:
                    json.loads(fn_args)
                    args_str = fn_args
                except Exception:
                    args_str = json.dumps({"input": fn_args}, ensure_ascii=False)
            else:
                args_str = json.dumps(fn_args if isinstance(fn_args, dict) else {}, ensure_ascii=False)

            extracted_calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": args_str,
                    },
                }
            )
            cleaned_text = cleaned_text.replace(m.group(0), "").strip()

        # Strip residual [ASSISTANT] wrapper tags if the model echoed them
        cleaned_text = re.sub(r"^\[ASSISTANT\]\s*", "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\s*\[/ASSISTANT\]$", "", cleaned_text, flags=re.IGNORECASE).strip()

        return extracted_calls, cleaned_text

    @classmethod
    def build_openai_chat_completion(
        cls,
        raw_text: str,
        model: str,
        thoughts_text: str = "",
        prompt_text: str = "",
    ) -> Dict[str, Any]:
        """Build a complete OpenAI ChatCompletion response dictionary from Gemini Web output."""
        tool_calls, cleaned_content = cls.extract_tool_calls_and_clean_text(raw_text)

        message: Dict[str, Any] = {
            "role": "assistant",
            "content": cleaned_content if (cleaned_content or not tool_calls) else None,
        }
        if thoughts_text and thoughts_text.strip():
            message["reasoning_content"] = thoughts_text.strip()
            message["reasoning"] = thoughts_text.strip()

        finish_reason = "stop"
        if tool_calls:
            message["tool_calls"] = tool_calls
            finish_reason = "tool_calls"

        prompt_tokens = max(1, len(prompt_text) // 4)
        completion_tokens = max(1, (len(raw_text) + len(thoughts_text or "")) // 4)

        return {
            "id": f"chatcmpl-gweb-{uuid.uuid4().hex[:20]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
