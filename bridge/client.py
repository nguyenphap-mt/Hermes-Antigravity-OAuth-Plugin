"""Antigravity Code Assist client and request/response translator.

Implements:
- Antigravity IDE HTTP headers & client fingerprint simulation.
- Two-way translation between OpenAI Chat Completions API and Gemini Code Assist API.
- Multi-step tool use, function call translation, and Gemini 3 thought signature handling.
- Server-Sent Events (SSE) streaming adapter.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from .auth import (
    AntigravityAuthManager,
    AntigravityCredentials,
    DEFAULT_PROJECT_ID,
)

logger = logging.getLogger(__name__)

# Endpoints
CODE_ASSIST_BASE_URL = "https://daily-cloudcode-pa.googleapis.com/v1internal"
FALLBACK_CODE_ASSIST_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"

# Supported model catalogue (matching Antigravity IDE)
ANTIGRAVITY_SUPPORTED_MODELS = [
    {
        "id": "gemini-3.7-flash",
        "name": "Gemini 3.7 Flash High",
        "code_assist_model": "gemini-3-flash-agent",
        "description": "Gemini 3.7 Flash with high reasoning budget and full tool use.",
    },
    {
        "id": "gemini-3.7-flash-medium",
        "name": "Gemini 3.7 Flash Medium",
        "code_assist_model": "gemini-3-flash-agent",
        "description": "Gemini 3.7 Flash with medium reasoning budget.",
    },
    {
        "id": "gemini-3.7-flash-low",
        "name": "Gemini 3.7 Flash Low",
        "code_assist_model": "gemini-3-flash-agent",
        "description": "Gemini 3.7 Flash with minimal reasoning latency.",
    },
    {
        "id": "gemini-3.6-flash",
        "name": "Gemini 3.6 Flash Medium",
        "code_assist_model": "gemini-3.6-flash-medium",
        "description": "Gemini 3.6 Flash with medium reasoning budget.",
    },
    {
        "id": "gemini-3.5-flash",
        "name": "Gemini 3.5 Flash Medium",
        "code_assist_model": "gemini-3.5-flash-medium",
        "description": "Gemini 3.5 Flash low-latency daily driver.",
    },
    {
        "id": "gemini-3.1-pro",
        "name": "Gemini 3.1 Pro Low",
        "code_assist_model": "gemini-3.1-pro-low",
        "description": "Gemini 3.1 Pro architecture and refactoring model.",
    },
    {
        "id": "claude-sonnet-4-6",
        "name": "Claude Sonnet 4.6 (Thinking)",
        "code_assist_model": "claude-sonnet-4-6",
        "description": "Claude 3.7 / 4.6 Sonnet with extended thinking via Antigravity.",
    },
    {
        "id": "claude-opus-4-6",
        "name": "Claude Opus 4.6 (Thinking)",
        "code_assist_model": "claude-opus-4-6",
        "description": "Claude 3.7 / 4.6 Opus with deep reasoning via Antigravity.",
    },
    {
        "id": "gpt-oss-120b",
        "name": "GPT-OSS 120B (Medium)",
        "code_assist_model": "gpt-oss-120b",
        "description": "GPT-OSS 120B open-weights model via Antigravity.",
    },
]

MODEL_ALIAS_MAP = {
    # Gemini 3.7 Flash — IDE shows "Gemini 3.7 Flash Medium"
    "gemini-3.7-flash": "gemini-3-flash-agent",
    "gemini-3-flash": "gemini-3-flash-agent",
    "gemini-3.7-flash-high": "gemini-3-flash-agent",
    "gemini-3.7-flash-medium": "gemini-3-flash-agent",
    "gemini-3.7-flash-low": "gemini-3-flash-agent",
    # Gemini 3.7 Pro — NOT in IDE, map to flash as fallback
    "gemini-3.7-pro": "gemini-3-flash-agent",
    "gemini-3-pro": "gemini-3-flash-agent",
    "gemini-pro": "gemini-3-flash-agent",
    # Gemini 3.6 Flash
    "gemini-3.6-flash": "gemini-3.6-flash-medium",
    "gemini-3.6-flash-medium": "gemini-3.6-flash-medium",
    # Gemini 3.5 Flash
    "gemini-3.5-flash": "gemini-3-flash-agent",
    "gemini-3.5-flash-medium": "gemini-3-flash-agent",
    "gemini-2.5-flash": "gemini-3-flash-agent",
    # Gemini 3.1 Pro
    "gemini-3.1-pro": "gemini-3.1-pro-low",
    "gemini-3.1-pro-low": "gemini-3.1-pro-low",
    "gemini-2.5-pro": "gemini-3.1-pro-low",
    # Claude Sonnet 4.6
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-3-7-sonnet": "claude-sonnet-4-6",
    "claude-3.7-sonnet": "claude-sonnet-4-6",
    # Claude Opus 4.6 — maps to sonnet (opus not always available)
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-opus-4.6": "claude-sonnet-4-6",
    "claude-3-7-opus": "claude-sonnet-4-6",
    "claude-3.7-opus": "claude-sonnet-4-6",
    # GPT-OSS 120B — Antigravity may not always advertise this model; if
        # the upstream rejects the request we fall back to the flash agent so
        # the user still gets a usable response instead of a hard error.
        "gpt-oss-120b": "gemini-3-flash-agent",
}


VALID_CODE_ASSIST_MODELS = {
    "gemini-3-flash-agent",
    "gemini-3.6-flash-medium",
    "gemini-3.1-pro-low",
    "claude-sonnet-4-6",
}


def map_model_name(requested_model: str) -> str:
    """Map user-requested model slug to Code Assist internal model identifier."""
    if not requested_model:
        return "gemini-3-flash-agent"
    normalized = requested_model.lower().strip()
    # Strip prefix if user passed "antigravity/model" or "google/model" or "nvidia/model"
    if "/" in normalized:
        normalized = normalized.split("/", 1)[1]
    mapped = MODEL_ALIAS_MAP.get(normalized, normalized)
    if mapped not in VALID_CODE_ASSIST_MODELS:
        logger.warning("Unknown model '%s' requested via Antigravity, falling back to gemini-3-flash-agent", requested_model)
        return "gemini-3-flash-agent"
    return mapped


def build_antigravity_headers(access_token: str, project_id: str = "") -> Dict[str, str]:
    """Generate HTTP headers simulating Antigravity IDE."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Antigravity/1.0.0 (Windows NT 10.0; Win64; x64) Code-Assist/2026.x",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1 gccl/antigravity-ide",
        "Client-Metadata": json.dumps({
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }, separators=(",", ":")),
        "x-activity-request-id": str(uuid.uuid4()),
    }
    return headers


# =============================================================================
# OpenAI to Gemini Translation
# =============================================================================

def _coerce_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: List[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                pieces.append(part["text"])
        return "\n".join(pieces)
    return str(content)


def _coerce_content_to_parts(content: Any) -> List[Dict[str, Any]]:
    """Convert OpenAI/Anthropic/Gemini multimodal content to Gemini parts format.

    Handles text, image_url (base64 data URI or dict), Anthropic base64 source,
    native inlineData, and mixed content arrays.
    """
    if content is None:
        return []
    if isinstance(content, str):
        return [{"text": content}] if content else []
    if isinstance(content, list):
        parts: List[Dict[str, Any]] = []
        for part in content:
            if isinstance(part, str):
                if part:
                    parts.append({"text": part})
            elif isinstance(part, dict):
                ptype = str(part.get("type", ""))
                if ptype == "text" and isinstance(part.get("text"), str):
                    if part["text"]:
                        parts.append({"text": part["text"]})
                elif ptype == "image_url" or "image_url" in part:
                    img_val = part.get("image_url")
                    url = img_val.get("url") if isinstance(img_val, dict) else (img_val if isinstance(img_val, str) else "")
                    if isinstance(url, str) and url.startswith("data:"):
                        try:
                            header, encoded = url.split(",", 1)
                            mime = header.split(":", 1)[1].split(";", 1)[0]
                            parts.append({
                                "inlineData": {
                                    "mimeType": mime or "image/jpeg",
                                    "data": encoded,
                                }
                            })
                        except Exception:
                            pass
                elif ptype == "image" and isinstance(part.get("source"), dict):
                    src = part["source"]
                    if src.get("type") == "base64" and src.get("data"):
                        parts.append({
                            "inlineData": {
                                "mimeType": src.get("media_type") or "image/jpeg",
                                "data": src["data"],
                            }
                        })
                elif "inlineData" in part and isinstance(part["inlineData"], dict):
                    parts.append({"inlineData": part["inlineData"]})
                elif "text" in part and isinstance(part["text"], str):
                    if part["text"]:
                        parts.append({"text": part["text"]})
        return parts
    text = str(content)
    return [{"text": text}] if text else []


def _translate_tool_call_to_gemini(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    fn = tool_call.get("function") or {}
    args_raw = fn.get("arguments", "")
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) and args_raw else {}
    except Exception:
        args = {"_raw": args_raw}
    if not isinstance(args, dict):
        args = {"_value": args}

    function_call: Dict[str, Any] = {
        "name": fn.get("name") or "",
        "args": args,
    }
    if tool_call.get("id"):
        function_call["id"] = str(tool_call["id"])

    result: Dict[str, Any] = {
        "functionCall": function_call,
    }
    # Code Assist REQUIRES thoughtSignature on every functionCall part.
    # Try to extract the real signature from Hermes' extra_content field
    # (stored as tool_call.extra_content.google.thought_signature).
    ts = tool_call.get("thoughtSignature")
    if not ts:
        extra = tool_call.get("extra_content")
        if isinstance(extra, dict):
            google = extra.get("google") or extra.get("thought_signature")
            if isinstance(google, dict):
                ts = google.get("thought_signature") or google.get("thoughtSignature")
    # Fallback: Code Assist requires this field, use validator skip token
    result["thoughtSignature"] = ts or "skip_thought_signature_validator"
    return result


def _translate_tool_result_to_gemini(message: Dict[str, Any]) -> Dict[str, Any]:
    name = str(message.get("name") or message.get("tool_call_id") or "tool")
    content = _coerce_content_to_text(message.get("content"))
    try:
        parsed = json.loads(content) if content.strip().startswith(("{", "[")) else None
    except Exception:
        parsed = None
    response = parsed if isinstance(parsed, dict) else {"output": content}
    function_response: Dict[str, Any] = {
        "name": name,
        "response": response,
    }
    if message.get("tool_call_id"):
        function_response["id"] = str(message["tool_call_id"])
    return {"functionResponse": function_response}


def _translate_tools_to_gemini(tools: Any) -> List[Dict[str, Any]]:
    if not isinstance(tools, list) or not tools:
        return []
    declarations: List[Dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") or {}
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name:
            continue
        decl: Dict[str, Any] = {"name": str(name)}
        if fn.get("description"):
            decl["description"] = str(fn["description"])
        params = fn.get("parameters")
        if isinstance(params, dict):
            decl["parameters"] = params
        declarations.append(decl)
    if not declarations:
        return []
    return [{"functionDeclarations": declarations}]


def _translate_tool_choice_to_gemini(tool_choice: Any) -> Optional[Dict[str, Any]]:
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        if tool_choice == "required":
            return {"functionCallingConfig": {"mode": "ANY"}}
        if tool_choice == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function") or {}
        name = fn.get("name")
        if name:
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [str(name)],
                },
            }
    return None


def _extract_tool_calls_from_text(text: str) -> tuple[List[Dict[str, Any]], str]:
    """Parse text formatted like [Tool call: func_name(args)] or Action: Called func_name(args) into real tool calls."""
    patterns = [
        re.compile(r'\[Tool call:\s*([a-zA-Z0-9_\-\.]+)\s*\((.*?)\)\]', re.DOTALL),
        re.compile(r'Action:\s*(?:Called\s+)?([a-zA-Z0-9_\-\.]+)\s*\((.*?)\)', re.DOTALL),
    ]
    tool_calls = []
    cleaned_text = text
    for pattern in patterns:
        matches = list(pattern.finditer(cleaned_text))
        for m in matches:
            fn_name = m.group(1).strip()
            raw_args = m.group(2).strip()
            parsed_args = {}
            if raw_args:
                try:
                    parsed_args = json.loads(raw_args)
                except Exception:
                    try:
                        import ast
                        parsed_args = ast.literal_eval(raw_args)
                    except Exception:
                        parsed_args = {"_raw": raw_args}
            if not isinstance(parsed_args, dict):
                parsed_args = {"_value": parsed_args}
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": fn_name,
                    "arguments": json.dumps(parsed_args, ensure_ascii=False),
                },
            })
        cleaned_text = pattern.sub("", cleaned_text).strip()
    return tool_calls, cleaned_text


def build_code_assist_request(
    openai_payload: Dict[str, Any],
    project_id: str,
) -> Dict[str, Any]:
    """Convert an OpenAI /v1/chat/completions payload to Code Assist envelope format."""
    messages = openai_payload.get("messages") or []
    model_name = map_model_name(openai_payload.get("model") or "gemini-3.7-flash")

    system_text_parts: List[str] = []
    contents: List[Dict[str, Any]] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user")

        if role == "system":
            text = _coerce_content_to_text(msg.get("content"))
            if text:
                system_text_parts.append(text)
            continue

        if role in {"tool", "function"}:
            # Convert tool results to text to avoid orphaned functionResponse
            # parts when their functionCall counterparts lack real thoughtSignature.
            tool_text = _coerce_content_to_text(msg.get("content"))
            tool_name = msg.get("name") or msg.get("tool_call_id") or "tool"
            contents.append({
                "role": "user",
                "parts": [{"text": f"[Tool result from {tool_name}: {tool_text[:2000]}]"}],
            })
            continue

        gemini_role = "model" if role == "assistant" else "user"
        parts: List[Dict[str, Any]] = []

        # Use multimodal-aware converter for user/assistant content
        content_parts = _coerce_content_to_parts(msg.get("content"))
        parts.extend(content_parts)

        tool_calls = msg.get("tool_calls") or []
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    # Check if this tool call has a REAL thoughtSignature
                    # (not the fake "skip_thought_signature_validator" fallback)
                    sig = tc.get("thoughtSignature") or ""
                    if not sig or sig == "skip_thought_signature_validator":
                        extra = tc.get("extra_content")
                        if isinstance(extra, dict):
                            google = extra.get("google") or extra.get("thought_signature")
                            if isinstance(google, dict):
                                sig = google.get("thought_signature") or google.get("thoughtSignature") or ""
                        if sig == "skip_thought_signature_validator":
                            sig = ""
                    if sig:
                        # Real Gemini signature — use native functionCall format
                        parts.append(_translate_tool_call_to_gemini(tc))
                    else:
                        # No real signature — convert to text
                        fn = tc.get("function") or {}
                        fn_name = fn.get("name", "unknown")
                        fn_args = fn.get("arguments", "{}")
                        parts.append({"text": f"[Tool call: {fn_name}({fn_args})]"})

        if parts:
            contents.append({"role": gemini_role, "parts": parts})

    # Pre-compute system text for fallback and later systemInstruction
    joined_system = "\n".join(p for p in system_text_parts if p).strip()

    if not contents:
        fallback_text = joined_system or "Hello"
        contents.append({"role": "user", "parts": [{"text": fallback_text}]})

    # Gemini requires strict role alternation (user/model/user/model...).
    # Long OpenAI conversations can produce consecutive same-role messages
    # when assistant messages with content=None are dropped. Merge them.
    merged: List[Dict[str, Any]] = []
    for entry in contents:
        if merged and merged[-1]["role"] == entry["role"]:
            merged[-1]["parts"].extend(entry["parts"])
        else:
            merged.append(entry)
    contents = merged

    # Ensure conversation starts with "user" role (Gemini requirement)
    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "(conversation context)"}]})

    generation_config: Dict[str, Any] = {}
    if "temperature" in openai_payload and openai_payload["temperature"] is not None:
        generation_config["temperature"] = float(openai_payload["temperature"])
    if "top_p" in openai_payload and openai_payload["top_p"] is not None:
        generation_config["topP"] = float(openai_payload["top_p"])
    if "max_tokens" in openai_payload and openai_payload["max_tokens"] is not None:
        generation_config["maxOutputTokens"] = int(openai_payload["max_tokens"])
    elif "max_completion_tokens" in openai_payload and openai_payload["max_completion_tokens"] is not None:
        generation_config["maxOutputTokens"] = int(openai_payload["max_completion_tokens"])

    inner_request: Dict[str, Any] = {
        "contents": contents,
    }
    if generation_config:
        inner_request["generationConfig"] = generation_config

    if joined_system:
        inner_request["systemInstruction"] = {
            "role": "system",
            "parts": [{"text": joined_system}],
        }

    gemini_tools = _translate_tools_to_gemini(openai_payload.get("tools"))
    if gemini_tools:
        inner_request["tools"] = gemini_tools

    tool_config = _translate_tool_choice_to_gemini(openai_payload.get("tool_choice"))
    if tool_config:
        inner_request["toolConfig"] = tool_config

    return {
        "project": project_id or DEFAULT_PROJECT_ID,
        "model": model_name,
        "user_prompt_id": str(uuid.uuid4()),
        "request": inner_request,
    }


# =============================================================================
# Gemini to OpenAI Response Translation
# =============================================================================

def translate_gemini_to_openai_response(
    gemini_resp: Dict[str, Any],
    requested_model: str,
) -> Dict[str, Any]:
    """Translate a non-streaming Code Assist / Gemini response to OpenAI format."""
    inner = gemini_resp.get("response") if isinstance(gemini_resp.get("response"), dict) else gemini_resp
    candidates = inner.get("candidates") or []

    content_text = ""
    reasoning_text = ""
    tool_calls: List[Dict[str, Any]] = []

    if candidates and isinstance(candidates[0], dict):
        cand = candidates[0]
        content_obj = cand.get("content") or {}
        parts = content_obj.get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("thought") is True and isinstance(part.get("text"), str):
                reasoning_text += part["text"]
            elif "text" in part and isinstance(part["text"], str):
                content_text += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_call_id = fc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                ts = part.get("thoughtSignature") or (fc.get("thoughtSignature") if isinstance(fc, dict) else None)
                tc_item: Dict[str, Any] = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": fc.get("name") or "",
                        "arguments": json.dumps(fc.get("args") or {}),
                    },
                }
                if ts:
                    tc_item["thoughtSignature"] = ts
                    tc_item["extra_content"] = {"google": {"thought_signature": ts}}
                tool_calls.append(tc_item)

    # Fallback: if model emitted [Tool call: name(args)] in content_text instead of structured functionCall
    if not tool_calls and content_text and "[Tool call:" in content_text:
        extracted_calls, cleaned_text = _extract_tool_calls_from_text(content_text)
        if extracted_calls:
            tool_calls = extracted_calls
            content_text = cleaned_text

    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content_text if content_text or not tool_calls else None,
    }
    if reasoning_text:
        message["reasoning_content"] = reasoning_text
    if tool_calls:
        message["tool_calls"] = tool_calls

    finish_reason = "tool_calls" if tool_calls else "stop"

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": requested_model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def translate_gemini_stream_event(
    event_data: Dict[str, Any],
    requested_model: str,
    stream_id: str,
) -> Optional[Dict[str, Any]]:
    """Translate one Gemini streaming SSE event into an OpenAI chat completion chunk."""
    inner = event_data.get("response") if isinstance(event_data.get("response"), dict) else event_data
    candidates = inner.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return None

    cand = candidates[0]
    content_obj = cand.get("content") or {}
    parts = content_obj.get("parts") or []

    delta: Dict[str, Any] = {}
    content_piece = ""
    reasoning_piece = ""
    tool_calls: List[Dict[str, Any]] = []

    for idx, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        if part.get("thought") is True and isinstance(part.get("text"), str):
            reasoning_piece += part["text"]
        elif "text" in part and isinstance(part["text"], str):
            content_piece += part["text"]
        elif "functionCall" in part:
            fc = part["functionCall"]
            ts = part.get("thoughtSignature") or (fc.get("thoughtSignature") if isinstance(fc, dict) else None)
            tc_item: Dict[str, Any] = {
                "index": idx,
                "id": fc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": fc.get("name") or "",
                    "arguments": json.dumps(fc.get("args") or {}),
                },
            }
            if ts:
                tc_item["thoughtSignature"] = ts
                tc_item["extra_content"] = {"google": {"thought_signature": ts}}
            tool_calls.append(tc_item)

    if content_piece:
        delta["content"] = content_piece
    if reasoning_piece:
        delta["reasoning_content"] = reasoning_piece
    if tool_calls:
        delta["tool_calls"] = tool_calls

    if not delta:
        return None

    finish_reason = cand.get("finishReason")
    openai_finish_reason = "stop" if finish_reason == "STOP" else None
    if tool_calls:
        openai_finish_reason = "tool_calls"

    return {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": requested_model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": openai_finish_reason,
            }
        ],
    }


class AntigravityClient:
    """HTTP Client executing requests against Google Code Assist backend."""

    def __init__(self, auth_manager: Optional[AntigravityAuthManager] = None) -> None:
        self.auth_manager = auth_manager or AntigravityAuthManager()
        self._http = httpx.AsyncClient(timeout=120.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def create_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        bearer_token: str = "",
    ) -> Dict[str, Any]:
        """Execute a non-streaming chat completion."""
        creds = self.auth_manager.resolve_valid_credentials(bearer_token=bearer_token)
        envelope = build_code_assist_request(openai_payload, creds.project_id)
        headers = build_antigravity_headers(creds.access_token, creds.project_id)

        url = f"{CODE_ASSIST_BASE_URL}:generateContent"
        resp = await self._http.post(url, json=envelope, headers=headers)
        if resp.status_code != 200:
            logger.warning("Primary Code Assist endpoint returned %s, trying fallback", resp.status_code)
            fallback_url = f"{FALLBACK_CODE_ASSIST_BASE_URL}:generateContent"
            resp = await self._http.post(fallback_url, json=envelope, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Antigravity Code Assist failed with HTTP {resp.status_code}: {resp.text}"
                )

        gemini_data = resp.json()
        requested_model = openai_payload.get("model") or "gemini-3.7-flash"
        return translate_gemini_to_openai_response(gemini_data, requested_model)

    async def stream_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        bearer_token: str = "",
    ) -> AsyncIterator[str]:
        """Stream chat completion as Server-Sent Events (SSE)."""
        creds = self.auth_manager.resolve_valid_credentials(bearer_token=bearer_token)
        envelope = build_code_assist_request(openai_payload, creds.project_id)
        headers = build_antigravity_headers(creds.access_token, creds.project_id)
        headers["Accept"] = "text/event-stream"

        stream_id = f"chatcmpl-{uuid.uuid4().hex}"
        requested_model = openai_payload.get("model") or "gemini-3.7-flash"

        url = f"{CODE_ASSIST_BASE_URL}:streamGenerateContent?alt=sse"

        async with self._http.stream("POST", url, json=envelope, headers=headers) as response:
            if response.status_code != 200:
                body = await response.aread()
                # Debug: log payload structure on 400 errors
                if response.status_code == 400:
                    contents = envelope.get("request", {}).get("contents", [])
                    roles = [c.get("role", "?") for c in contents]
                    # Find consecutive same-role pairs
                    violations = []
                    for i in range(1, len(roles)):
                        if roles[i] == roles[i-1]:
                            violations.append(f"[{i-1}:{roles[i-1]},{i}:{roles[i]}]")
                    # Find empty parts
                    empty_parts = [i for i, c in enumerate(contents) if not c.get("parts")]
                    # Check for parts with unsupported content
                    part_types = set()
                    for c in contents:
                        for p in c.get("parts", []):
                            part_types.update(p.keys())
                    logger.error(
                        "DEBUG 400: contents=%d, roles_start=%s, roles_end=%s, "
                        "violations=%s, empty_parts=%s, part_types=%s, "
                        "model=%s, first_role=%s, last_role=%s",
                        len(contents),
                        roles[:5], roles[-5:],
                        violations[:10] if violations else "none",
                        empty_parts[:10] if empty_parts else "none",
                        part_types,
                        envelope.get("model", "?"),
                        roles[0] if roles else "?",
                        roles[-1] if roles else "?",
                    )
                    # Dump payload structure (not full content) for analysis
                    try:
                        debug_dump = []
                        for i, c in enumerate(contents):
                            parts_info = []
                            for p in c.get("parts", []):
                                pinfo = {k: (str(v)[:50] if isinstance(v, str) else type(v).__name__)
                                         for k, v in p.items()}
                                parts_info.append(pinfo)
                            debug_dump.append({
                                "idx": i,
                                "role": c.get("role"),
                                "num_parts": len(c.get("parts", [])),
                                "parts": parts_info,
                            })
                        import tempfile
                        dump_path = os.path.join(
                            tempfile.gettempdir(), "antigravity_debug_400.json"
                        )
                        with open(dump_path, "w", encoding="utf-8") as f:
                            json.dump(debug_dump, f, indent=2, ensure_ascii=False)
                        logger.error("DEBUG 400: payload structure dumped to %s", dump_path)
                    except Exception as dump_err:
                        logger.error("DEBUG 400: failed to dump: %s", dump_err)
                raise RuntimeError(
                    f"Antigravity Code Assist streaming failed with HTTP {response.status_code}: {body.decode('utf-8', 'replace')}"
                )

            # Emit initial chunk with role once connection is verified
            initial_chunk = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": requested_model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(initial_chunk)}\n\n"

            buffer = ""
            async for raw_chunk in response.aiter_text():
                # Normalize line endings: Google Code Assist SSE uses \r\r\n instead of \n\n
                buffer += raw_chunk.replace("\r\n", "\n").replace("\r", "\n")
                while "\n\n" in buffer:
                    event_block, buffer = buffer.split("\n\n", 1)
                    for line in event_block.split("\n"):
                        line = line.strip()
                        if line.startswith("data:"):
                            raw_json = line[5:].strip()
                            if not raw_json or raw_json == "[DONE]":
                                continue
                            try:
                                event_obj = json.loads(raw_json)
                                chunk = translate_gemini_stream_event(
                                    event_obj, requested_model, stream_id
                                )
                                if chunk:
                                    yield f"data: {json.dumps(chunk)}\n\n"
                            except Exception as e:
                                logger.debug("Failed to parse SSE event: %s", e)

        # Final end chunk
        final_chunk = {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": requested_model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"
