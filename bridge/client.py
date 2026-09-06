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

try:
    from tools.antigravity_bridge.auth import (
        AntigravityAuthManager,
        AntigravityCredentials,
        DEFAULT_PROJECT_ID,
    )
except ImportError:
    from .auth import (
        AntigravityAuthManager,
        AntigravityCredentials,
        DEFAULT_PROJECT_ID,
    )

try:
    from tools.antigravity_bridge.models import ModelDiscoveryManager
except ImportError:
    from .models import ModelDiscoveryManager

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
    # GPT-OSS 120B — maps to flash as safe fallback
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
    """Generate HTTP headers simulating Antigravity IDE using dynamic fingerprinting."""
    try:
        from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
        return AntigravityFingerprint.build_headers(access_token, project_id=project_id)
    except ImportError:
        try:
            from bridge.fingerprint import AntigravityFingerprint
            return AntigravityFingerprint.build_headers(access_token, project_id=project_id)
        except Exception:
            pass

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Antigravity/2.11.0 (Windows NT 10.0; Win64; x64) Code-Assist/2026.03.0",
        "X-Goog-Api-Client": "gl-go/1.24.0 gccl/2.11.0 antigravity/2.11.0",
        "Client-Metadata": json.dumps({
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_WINDOWS",
            "pluginType": "GEMINI",
            "applicationVersion": "2.11.0",
        }, separators=(",", ":")),
        "x-activity-request-id": str(uuid.uuid4()),
    }


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


def _clean_schema_for_gemini(val: Any) -> Any:
    """Sanitize JSON Schema / OpenAPI schema to be strictly compliant with Google Gemini / Code Assist Protobuf schema.

    Google Cloud Code Assist uses a strict protobuf Schema parser that rejects unknown fields
    such as 'exclusiveMinimum', 'exclusiveMaximum', '$schema', 'patternProperties', 'additionalProperties', etc.
    with HTTP 400 INVALID_ARGUMENT.

    This function recursively traverses the schema and cleans it safely while preserving constraints.
    """
    if not isinstance(val, dict):
        if isinstance(val, list):
            return [_clean_schema_for_gemini(x) for x in val]
        return val

    DISALLOWED_GEMINI_FIELDS = {
        "exclusiveMinimum",
        "exclusiveMaximum",
        "$schema",
        "$id",
        "$ref",
        "patternProperties",
        "additionalProperties",
        "definitions",
        "$defs",
    }

    cleaned: Dict[str, Any] = {}
    for k, v in val.items():
        if k in DISALLOWED_GEMINI_FIELDS:
            # Map exclusive bounds to inclusive bounds if not already defined
            if k == "exclusiveMinimum" and isinstance(v, (int, float)) and "minimum" not in val:
                cleaned["minimum"] = v
            elif k == "exclusiveMaximum" and isinstance(v, (int, float)) and "maximum" not in val:
                cleaned["maximum"] = v
            continue
        cleaned[k] = _clean_schema_for_gemini(v)
    return cleaned


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
            decl["parameters"] = _clean_schema_for_gemini(params)
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
    model_discovery: Optional[ModelDiscoveryManager] = None,
) -> Dict[str, Any]:
    """Convert an OpenAI /v1/chat/completions payload to Code Assist envelope format."""
    messages = openai_payload.get("messages") or []
    req_model = openai_payload.get("model") or "gemini-3.7-flash"
    model_meta: Dict[str, Any] = {}
    if model_discovery is not None:
        model_name, model_meta = model_discovery.resolve_model(req_model)
    else:
        model_name = map_model_name(req_model)

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
    # Auto-inject thinkingConfig if model supports thinking
    if model_meta.get("supports_thinking"):
        budget = model_meta.get("thinking_budget", 2048)
        user_budget = openai_payload.get("thinking_budget")
        if user_budget:
            try:
                budget = int(user_budget)
            except Exception:
                pass
        generation_config["thinkingConfig"] = {"thinkingBudget": budget}

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

    if not content_text and not tool_calls and reasoning_text:
        content_text = reasoning_text

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

    def __init__(
        self,
        auth_manager: Optional[AntigravityAuthManager] = None,
        model_discovery: Optional[ModelDiscoveryManager] = None,
    ) -> None:
        self.auth_manager = auth_manager or AntigravityAuthManager()
        self.model_discovery = model_discovery or ModelDiscoveryManager(self.auth_manager)
        try:
            from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
        except ImportError:
            from bridge.account_pool import AntigravityAccountPoolManager
        self.account_pool = AntigravityAccountPoolManager(storage_path=self.auth_manager.auth_file)
        self._http = httpx.AsyncClient(timeout=120.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def create_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        bearer_token: str = "",
    ) -> Dict[str, Any]:
        """Execute a non-streaming chat completion with multi-account auto-failover."""
        attempted_emails = set()
        accounts = self.account_pool.list_accounts()
        max_attempts = max(1, len(accounts)) if not bearer_token else 1
        last_error = None

        for attempt in range(max_attempts):
            if not bearer_token:
                if attempted_emails:
                    next_acc = self.account_pool.get_account_for_service("llm", exclude_emails=attempted_emails)
                    if not next_acc:
                        break
                    creds = self.auth_manager.resolve_valid_credentials(bearer_token=next_acc.email)
                else:
                    chosen_acc = self.account_pool.get_account_for_service("llm")
                    if chosen_acc:
                        creds = self.auth_manager.resolve_valid_credentials(bearer_token=chosen_acc.email)
                    else:
                        creds = self.auth_manager.resolve_valid_credentials(bearer_token="")
            else:
                creds = self.auth_manager.resolve_valid_credentials(bearer_token=bearer_token)

            if not creds:
                break

            current_email = (creds.email or "default").strip().lower()
            attempted_emails.add(current_email)

            # Apply micro-spacing guard to avoid rapid concurrency bursts
            self.account_pool.enforce_micro_spacing(current_email, min_interval=1.0)

            envelope = build_code_assist_request(openai_payload, creds.project_id, self.model_discovery)
            headers = build_antigravity_headers(creds.access_token, creds.project_id)

            url = f"{CODE_ASSIST_BASE_URL}:generateContent"
            try:
                resp = await self._http.post(url, json=envelope, headers=headers)
                if resp.status_code != 200:
                    logger.warning("Primary Code Assist endpoint returned %s, trying fallback", resp.status_code)
                    fallback_url = f"{FALLBACK_CODE_ASSIST_BASE_URL}:generateContent"
                    resp = await self._http.post(fallback_url, json=envelope, headers=headers)

                # Single-account RandExpBackoff retry on 429
                if resp.status_code == 429 and max_attempts <= 1:
                    import random
                    for retry_idx in range(2):
                        backoff_delay = 1.5 * (2 ** retry_idx) + random.uniform(0.2, 0.6)
                        logger.info("Single-account rate limit: waiting %.2fs before RandExpBackoff retry %d...", backoff_delay, retry_idx + 1)
                        await asyncio.sleep(backoff_delay)
                        resp = await self._http.post(url, json=envelope, headers=headers)
                        if resp.status_code == 200:
                            break

                if resp.status_code == 200:
                    self.account_pool.record_account_usage(current_email, success=True)
                    gemini_data = resp.json()
                    requested_model = openai_payload.get("model") or "gemini-3.7-flash"
                    return translate_gemini_to_openai_response(gemini_data, requested_model)

                is_failover_code = resp.status_code in {429, 403, 503}
                if is_failover_code and not bearer_token and attempt < max_attempts - 1:
                    logger.warning(
                        "Account '%s' encountered HTTP %d (%s). Auto-failing over to next account in pool...",
                        current_email, resp.status_code, resp.text[:120]
                    )
                    self.account_pool.mark_account_exhausted(
                        current_email, reason=f"HTTP {resp.status_code}"
                    )
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    continue
                else:
                    self.account_pool.record_account_usage(current_email, success=False)
                    raise RuntimeError(
                        f"Antigravity Code Assist failed with HTTP {resp.status_code}: {resp.text}"
                    )
            except Exception as e:
                last_error = e
                if not bearer_token and attempt < max_attempts - 1:
                    logger.warning(
                        "Attempt %d failed on account '%s' (%s), failing over...",
                        attempt + 1, current_email, e
                    )
                    self.account_pool.mark_account_exhausted(
                        current_email, reason=str(e)
                    )
                    continue
                raise

        raise RuntimeError(f"All Antigravity accounts in pool exhausted. Last error: {last_error}")

    async def stream_chat_completion(
        self,
        openai_payload: Dict[str, Any],
        bearer_token: str = "",
    ) -> AsyncIterator[str]:
        """Stream chat completion as Server-Sent Events (SSE) with auto-failover on stream connection."""
        attempted_emails = set()
        accounts = self.account_pool.list_accounts()
        max_attempts = max(1, len(accounts)) if not bearer_token else 1
        last_error = None

        stream_id = f"chatcmpl-{uuid.uuid4().hex}"
        requested_model = openai_payload.get("model") or "gemini-3.7-flash"

        for attempt in range(max_attempts):
            if not bearer_token:
                if attempted_emails:
                    next_acc = self.account_pool.get_account_for_service("llm", exclude_emails=attempted_emails)
                    if not next_acc:
                        break
                    creds = self.auth_manager.resolve_valid_credentials(bearer_token=next_acc.email)
                else:
                    chosen_acc = self.account_pool.get_account_for_service("llm")
                    if chosen_acc:
                        creds = self.auth_manager.resolve_valid_credentials(bearer_token=chosen_acc.email)
                    else:
                        creds = self.auth_manager.resolve_valid_credentials(bearer_token="")
            else:
                creds = self.auth_manager.resolve_valid_credentials(bearer_token=bearer_token)

            if not creds:
                break

            current_email = (creds.email or "default").strip().lower()
            attempted_emails.add(current_email)

            # Apply micro-spacing guard
            self.account_pool.enforce_micro_spacing(current_email, min_interval=1.0)

            envelope = build_code_assist_request(openai_payload, creds.project_id, self.model_discovery)
            headers = build_antigravity_headers(creds.access_token, creds.project_id)
            headers["Accept"] = "text/event-stream"

            url = f"{CODE_ASSIST_BASE_URL}:streamGenerateContent?alt=sse"

            try:
                response = await self._http.send(
                    self._http.build_request("POST", url, json=envelope, headers=headers),
                    stream=True,
                )
                if response.status_code != 200:
                    fallback_url = f"{FALLBACK_CODE_ASSIST_BASE_URL}:streamGenerateContent?alt=sse"
                    await response.aclose()
                    response = await self._http.send(
                        self._http.build_request("POST", fallback_url, json=envelope, headers=headers),
                        stream=True,
                    )

                if response.status_code == 200:
                    self.account_pool.record_account_usage(current_email, success=True)
                    initial_chunk = {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(initial_chunk)}\n\n"

                    buffer = ""
                    try:
                        async for raw_chunk in response.aiter_text():
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
                    finally:
                        await response.aclose()

                    final_chunk = {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                else:
                    body = await response.aread()
                    await response.aclose()
                    is_failover_code = response.status_code in {429, 403, 503}
                    if is_failover_code and not bearer_token and attempt < max_attempts - 1:
                        logger.warning(
                            "Account '%s' encountered HTTP %d during streaming. Auto-failing over to next account...",
                            current_email, response.status_code
                        )
                        self.account_pool.mark_account_exhausted(
                            current_email, reason=f"HTTP {response.status_code}"
                        )
                        last_error = f"HTTP {response.status_code}: {body.decode('utf-8', 'replace')}"
                        continue
                    else:
                        self.account_pool.record_account_usage(current_email, success=False)
                        raise RuntimeError(
                            f"Antigravity Code Assist streaming failed with HTTP {response.status_code}: {body.decode('utf-8', 'replace')}"
                        )
            except Exception as e:
                last_error = e
                if not bearer_token and attempt < max_attempts - 1:
                    logger.warning(
                        "Stream attempt %d failed on account '%s' (%s), failing over...",
                        attempt + 1, current_email, e
                    )
                    self.account_pool.mark_account_exhausted(
                        current_email, reason=str(e)
                    )
                    continue
                raise

        raise RuntimeError(f"All Antigravity accounts exhausted for streaming. Last error: {last_error}")
