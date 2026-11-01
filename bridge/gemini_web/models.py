"""Model Registry, Header Builder, and Dynamic WIZ_global_data Scraper for Gemini Web App.

Supports:
- Gemini Argon (gemini-web-argon / gemini-3.0-argon)
- Gemini 2.5 Pro (gemini-web-2.5-pro)
- Gemini 2.5 Flash (gemini-web-2.5-flash)
- Gemini Web Default (gemini-web-default — uses whatever model is selected on the Web UI)
- Dynamic scraping of 16-character hex model descriptors from https://gemini.google.com/app HTML
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Baseline Gemini Web App models and their known BardFrontendService hex descriptors
GEMINI_WEB_MODELS: Dict[str, Dict[str, Any]] = {
    "gemini-web-4-argon": {
        "id": "gemini-web-4-argon",
        "displayName": "Gemini 4 Argon — Nhiệm vụ phức tạp (Web App)",
        "family": "argon",
        "default_hex": "9d8ca3786ebdfbea",
        "fallback_hexes": ["56fdd199312815e2", "61530e79959ab139"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "4 Argon (Nhiệm vụ phức tạp) via gemini.google.com/app consumer web quota.",
    },
    "gemini-web-4-argon-high": {
        "id": "gemini-web-4-argon-high",
        "displayName": "Gemini 4 Argon (High Thinking — Web App)",
        "family": "argon",
        "default_hex": "9d8ca3786ebdfbea",
        "fallback_hexes": ["56fdd199312815e2"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON_HIGH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "4 Argon (Cấp độ tư duy Cao / High) via gemini.google.com/app web quota.",
    },
    "gemini-web-4-argon-medium": {
        "id": "gemini-web-4-argon-medium",
        "displayName": "Gemini 4 Argon (Medium Thinking — Web App)",
        "family": "argon",
        "default_hex": "9d8ca3786ebdfbea",
        "fallback_hexes": ["56fdd199312815e2"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON_MEDIUM",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "4 Argon (Cấp độ tư duy Trung bình / Medium) via gemini.google.com/app web quota.",
    },
    "gemini-web-4-argon-low": {
        "id": "gemini-web-4-argon-low",
        "displayName": "Gemini 4 Argon (Low Thinking — Web App)",
        "family": "argon",
        "default_hex": "9d8ca3786ebdfbea",
        "fallback_hexes": ["56fdd199312815e2"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON_LOW",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "4 Argon (Cấp độ tư duy Nhanh / Low) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.1-pro": {
        "id": "gemini-web-3.1-pro",
        "displayName": "Gemini 3.1 Pro — Suy luận nâng cao (Web App)",
        "family": "pro",
        "default_hex": "61530e79959ab139",
        "fallback_hexes": ["9d8ca3786ebdfbea", "2525e3954d185b3c"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_31_PRO",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.1 Pro (Suy luận nâng cao) via gemini.google.com/app consumer web quota.",
    },
    "gemini-web-3.1-pro-high": {
        "id": "gemini-web-3.1-pro-high",
        "displayName": "Gemini 3.1 Pro (High Thinking — Web App)",
        "family": "pro",
        "default_hex": "61530e79959ab139",
        "fallback_hexes": ["9d8ca3786ebdfbea"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 10001,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_31_PRO_HIGH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.1 Pro (Cấp độ tư duy Cao / High) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.1-pro-low": {
        "id": "gemini-web-3.1-pro-low",
        "displayName": "Gemini 3.1 Pro (Low Thinking — Web App)",
        "family": "pro",
        "default_hex": "61530e79959ab139",
        "fallback_hexes": ["9d8ca3786ebdfbea"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1001,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_31_PRO_LOW",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.1 Pro (Cấp độ tư duy Nhanh / Low) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.8-flash": {
        "id": "gemini-web-3.8-flash",
        "displayName": "Gemini 3.8 Flash — Trợ giúp toàn diện (Web App)",
        "family": "flash",
        "default_hex": "9ec249fc9ad08861",
        "fallback_hexes": ["71c2d248d3b102ff"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.8 Flash (Trợ giúp toàn diện) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.8-flash-high": {
        "id": "gemini-web-3.8-flash-high",
        "displayName": "Gemini 3.8 Flash (High Thinking — Web App)",
        "family": "flash",
        "default_hex": "9ec249fc9ad08861",
        "fallback_hexes": ["71c2d248d3b102ff"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH_HIGH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.8 Flash (Cấp độ tư duy Cao / High) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.8-flash-medium": {
        "id": "gemini-web-3.8-flash-medium",
        "displayName": "Gemini 3.8 Flash (Medium Thinking — Web App)",
        "family": "flash",
        "default_hex": "9ec249fc9ad08861",
        "fallback_hexes": ["71c2d248d3b102ff"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH_MEDIUM",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.8 Flash (Cấp độ tư duy Trung bình / Medium) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.8-flash-low": {
        "id": "gemini-web-3.8-flash-low",
        "displayName": "Gemini 3.8 Flash (Low Thinking — Web App)",
        "family": "flash",
        "default_hex": "9ec249fc9ad08861",
        "fallback_hexes": ["71c2d248d3b102ff"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH_LOW",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.8 Flash (Cấp độ tư duy Nhanh / Low) via gemini.google.com/app web quota.",
    },
    "gemini-web-3.5-flash-lite": {
        "id": "gemini-web-3.5-flash-lite",
        "displayName": "Gemini 3.5 Flash-Lite — Câu trả lời nhanh nhất (Web App)",
        "family": "flash",
        "default_hex": "71c2d248d3b102ff",
        "fallback_hexes": ["9ec249fc9ad08861"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_35_FLASH_LITE",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "3.5 Flash-Lite (Câu trả lời nhanh nhất) via gemini.google.com/app web quota.",
    },
    "gemini-web-argon": {
        "id": "gemini-web-argon",
        "displayName": "Gemini Argon (Web App Pro/Ultra)",
        "family": "argon",
        "default_hex": "9d8ca3786ebdfbea",
        "fallback_hexes": ["56fdd199312815e2", "61530e79959ab139"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_ARGON",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "Gemini Argon (Pro/Ultra) via gemini.google.com/app consumer web quota.",
    },
    "gemini-web-2.5-pro": {
        "id": "gemini-web-2.5-pro",
        "displayName": "Gemini 2.5 Pro (Web App)",
        "family": "pro",
        "default_hex": "61530e79959ab139",
        "fallback_hexes": ["9d8ca3786ebdfbea", "2525e3954d185b3c"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_25_PRO",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "Gemini 2.5 Pro via gemini.google.com/app consumer web quota.",
    },
    "gemini-web-2.5-flash": {
        "id": "gemini-web-2.5-flash",
        "displayName": "Gemini 2.5 Flash (Web App)",
        "family": "flash",
        "default_hex": "9ec249fc9ad08861",
        "fallback_hexes": ["71c2d248d3b102ff"],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_25_FLASH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "Gemini 2.5 Flash high-speed inference via gemini.google.com/app web quota.",
    },
    "gemini-web-default": {
        "id": "gemini-web-default",
        "displayName": "Gemini Web Default (UI Selected Model)",
        "family": "argon",
        "default_hex": "",
        "fallback_hexes": [],
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": False,
        "model": "MODEL_GEMINI_WEB_DEFAULT",
        "apiProvider": "API_PROVIDER_GEMINI_WEB",
        "description": "Uses the active default model currently selected on gemini.google.com/app.",
    },
}

GEMINI_WEB_ALIASES: Dict[str, str] = {
    "gemini-web-4-argon": "gemini-web-4-argon",
    "gemini-web-4-argon-high": "gemini-web-4-argon-high",
    "gemini-web-4-argon-medium": "gemini-web-4-argon-medium",
    "gemini-web-4-argon-low": "gemini-web-4-argon-low",
    "gemini-web-3.1-pro": "gemini-web-3.1-pro",
    "gemini-web-3.1-pro-high": "gemini-web-3.1-pro-high",
    "gemini-web-3.1-pro-low": "gemini-web-3.1-pro-low",
    "gemini-web-3.8-flash": "gemini-web-3.8-flash",
    "gemini-web-3.8-flash-high": "gemini-web-3.8-flash-high",
    "gemini-web-3.8-flash-medium": "gemini-web-3.8-flash-medium",
    "gemini-web-3.8-flash-low": "gemini-web-3.8-flash-low",
    "gemini-web-3.5-flash-lite": "gemini-web-3.5-flash-lite",
    "gemini-web-flash-lite": "gemini-web-3.5-flash-lite",
    "gemini-web-argon": "gemini-web-argon",
    "gemini-argon": "gemini-web-argon",
    "gemini-3.0-argon": "gemini-web-argon",
    "gemini-3-argon": "gemini-web-argon",
    "gemini-web-3.0": "gemini-web-argon",
    "gemini-web-pro": "gemini-web-3.1-pro",
    "gemini-web-2.5-pro": "gemini-web-2.5-pro",
    "gemini-web-flash": "gemini-web-3.8-flash",
    "gemini-web-2.5-flash": "gemini-web-2.5-flash",
    "gemini-web-default": "gemini-web-default",
    "gemini-web": "gemini-web-4-argon",
}


def is_explicit_gemini_web_model(model_name: str) -> bool:
    """Return True if the model slug explicitly targets the Gemini Web App pool."""
    if not model_name:
        return False
    norm = model_name.strip().lower()
    if "/" in norm:
        norm = norm.split("/", 1)[1]
    return norm in GEMINI_WEB_ALIASES or norm.startswith("gemini-web")


def resolve_gemini_web_model(model_name: str) -> str:
    """Normalize any model identifier into a canonical GEMINI_WEB_MODELS key or dynamic gemini-web-* ID."""
    if not model_name:
        return "gemini-web-4-argon"
    norm = model_name.strip().lower()
    if "/" in norm:
        norm = norm.split("/", 1)[1]
    if norm in GEMINI_WEB_ALIASES:
        return GEMINI_WEB_ALIASES[norm]
    if norm in GEMINI_WEB_MODELS:
        return norm
    # Preserve any explicit dynamic gemini-web-* model ID (e.g. gemini-web-3.1-flash-lite, gemini-web-4.5-pro)
    if norm.startswith("gemini-web-") and len(norm) > len("gemini-web-"):
        return norm
    # Map standard Gemini models for web_first or hybrid_failover modes
    if "4-argon" in norm or "4_argon" in norm:
        if "low" in norm:
            return "gemini-web-4-argon-low"
        if "medium" in norm:
            return "gemini-web-4-argon-medium"
        if "high" in norm:
            return "gemini-web-4-argon-high"
        return "gemini-web-4-argon"
    if "argon" in norm or "3.8-pro" in norm or "3-pro" in norm or "3.7-pro" in norm:
        return "gemini-web-argon"
    if "3.1-pro" in norm:
        if "low" in norm:
            return "gemini-web-3.1-pro-low"
        if "high" in norm:
            return "gemini-web-3.1-pro-high"
        return "gemini-web-3.1-pro"
    if "pro" in norm:
        return "gemini-web-2.5-pro"
    if "3.5-flash-lite" in norm or "flash-lite" in norm or "lite" in norm:
        return "gemini-web-3.5-flash-lite"
    if "3.8-flash" in norm:
        if "low" in norm:
            return "gemini-web-3.8-flash-low"
        if "medium" in norm:
            return "gemini-web-3.8-flash-medium"
        if "high" in norm:
            return "gemini-web-3.8-flash-high"
        return "gemini-web-3.8-flash"
    if "flash" in norm:
        return "gemini-web-2.5-flash"
    return "gemini-web-4-argon"


def resolve_web_model_family(model_name: str) -> str:
    """Resolve model into quota bucket family: 'argon', 'pro', or 'flash'."""
    canonical = resolve_gemini_web_model(model_name)
    meta = GEMINI_WEB_MODELS.get(canonical, {})
    if meta.get("family"):
        return str(meta["family"])
    c_low = canonical.lower()
    if "flash" in c_low or "lite" in c_low:
        return "flash"
    if "pro" in c_low:
        return "pro"
    return "argon"


def build_model_selector_header(
    model_name: str,
    node_available_models: Optional[List[Dict[str, Any]]] = None,
    override_hex: Optional[str] = None,
) -> Optional[str]:
    """Build the x-goog-ext-525001261-jspb header value for BardFrontendService.

    Returns None when using gemini-web-default (omitting the header uses the account's UI default).
    """
    canonical = resolve_gemini_web_model(model_name)
    if canonical == "gemini-web-default" and not override_hex:
        return None

    chosen_hex = (override_hex or "").strip()
    if not chosen_hex and node_available_models:
        for item in node_available_models:
            if not isinstance(item, dict):
                continue
            if item.get("id") == canonical and item.get("hex_id"):
                chosen_hex = str(item["hex_id"]).strip()
                break

    if not chosen_hex:
        spec = GEMINI_WEB_MODELS.get(canonical, GEMINI_WEB_MODELS["gemini-web-4-argon"])
        chosen_hex = str(spec.get("default_hex") or "")

    if not chosen_hex:
        return None

    # Format required by BardFrontendService
    return json.dumps([1, None, None, None, chosen_hex, None, None, 0, [4]], separators=(",", ":"))


def scrape_models_and_tier_from_html(html: str) -> Dict[str, Any]:
    """Extract available models, hex IDs, user email, and plan tier from gemini.google.com/app HTML."""
    result: Dict[str, Any] = {
        "email": None,
        "detected_tier": "free",
        "models": [],
    }
    if not html:
        result["models"] = _default_node_models_list()
        return result

    # 1. Extract email if present in WIZ_global_data
    email_match = re.search(r'"([a-zA-Z0-9._%+-]+@(?:gmail\.com|googlemail\.com|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}))"', html)
    if email_match:
        candidate_email = email_match.group(1)
        if not candidate_email.endswith(".png") and not candidate_email.endswith(".svg"):
            result["email"] = candidate_email.lower()

    # 2. Detect tier (Ultra / Pro / Advanced / Argon / g1-pro-tier / Vietnamese UI "Pro" badge)
    html_lower = html.lower()
    if (
        "gemini ultra" in html_lower
        or "google ai ultra" in html_lower
        or "g1-ultra" in html_lower
        or "g1_ultra" in html_lower
    ):
        result["detected_tier"] = "ultra"
    elif (
        "gemini argon" in html_lower
        or "4 argon" in html_lower
        or "3.1 pro" in html_lower
        or "gemini advanced" in html_lower
        or "google one ai" in html_lower
        or "google ai pro" in html_lower
        or "g1-pro" in html_lower
        or "g1_pro" in html_lower
        or "2.5 pro" in html_lower
        or '"pro"' in html_lower
    ):
        result["detected_tier"] = "pro"

    # 3. Scrape [hex_id, display_name] pairs from inline JSON structures
    discovered_by_id: Dict[str, Dict[str, str]] = {}
    pair_pattern = re.compile(
        r'\["([0-9a-f]{16})"\s*,\s*"([^"]{2,48})"',
        re.IGNORECASE,
    )
    model_keyword_re = re.compile(
        r"(argon|pro|flash|lite|ultra|nano|thinking|reasoning|gemini|\b\d+\.\d+\b)",
        re.IGNORECASE,
    )
    for m in pair_pattern.finditer(html):
        hex_id = m.group(1).lower()
        label = m.group(2).strip()
        label_lower = label.lower()
        if "4 argon" in label_lower or ("argon" in label_lower and "4" in label_lower):
            discovered_by_id["gemini-web-4-argon"] = {
                "id": "gemini-web-4-argon",
                "label": label,
                "hex_id": hex_id,
            }
            discovered_by_id["gemini-web-argon"] = {
                "id": "gemini-web-argon",
                "label": label,
                "hex_id": hex_id,
            }
            if result["detected_tier"] == "free":
                result["detected_tier"] = "pro"
        elif "argon" in label_lower or "3.0" in label_lower or "ultra" in label_lower:
            discovered_by_id["gemini-web-argon"] = {
                "id": "gemini-web-argon",
                "label": label,
                "hex_id": hex_id,
            }
            discovered_by_id.setdefault(
                "gemini-web-4-argon",
                {"id": "gemini-web-4-argon", "label": label, "hex_id": hex_id},
            )
            if result["detected_tier"] == "free":
                result["detected_tier"] = "pro"
        elif "3.1" in label_lower and "pro" in label_lower:
            discovered_by_id["gemini-web-3.1-pro"] = {
                "id": "gemini-web-3.1-pro",
                "label": label,
                "hex_id": hex_id,
            }
            if result["detected_tier"] == "free":
                result["detected_tier"] = "pro"
        elif "pro" in label_lower or "thinking" in label_lower or "reasoning" in label_lower:
            discovered_by_id["gemini-web-2.5-pro"] = {
                "id": "gemini-web-2.5-pro",
                "label": label,
                "hex_id": hex_id,
            }
            if result["detected_tier"] == "free":
                result["detected_tier"] = "pro"
        elif "3.5" in label_lower and ("lite" in label_lower or "flash" in label_lower):
            discovered_by_id["gemini-web-3.5-flash-lite"] = {
                "id": "gemini-web-3.5-flash-lite",
                "label": label,
                "hex_id": hex_id,
            }
        elif "3.8" in label_lower and "flash" in label_lower:
            discovered_by_id["gemini-web-3.8-flash"] = {
                "id": "gemini-web-3.8-flash",
                "label": label,
                "hex_id": hex_id,
            }
        elif "flash" in label_lower:
            discovered_by_id["gemini-web-2.5-flash"] = {
                "id": "gemini-web-2.5-flash",
                "label": label,
                "hex_id": hex_id,
            }

        # Dynamic auto-slug for any new/future model label in WIZ_global_data (e.g. "4.5 Pro", "5 Argon")
        if model_keyword_re.search(label_lower):
            slug = re.sub(r"^gemini\s+", "", label_lower)
            slug = re.sub(r"[^a-z0-9.]+", "-", slug).strip("-")
            if slug:
                dyn_id = f"gemini-web-{slug}"
                discovered_by_id.setdefault(
                    dyn_id,
                    {"id": dyn_id, "label": label, "hex_id": hex_id},
                )

    # Merge discovered models with baseline defaults AND append any newly discovered dynamic models
    merged: List[Dict[str, str]] = []
    seen_ids = set()
    for base_item in _default_node_models_list():
        m_id = base_item["id"]
        seen_ids.add(m_id)
        if m_id in discovered_by_id:
            merged.append(discovered_by_id[m_id])
        else:
            merged.append(base_item)

    for dyn_id, dyn_item in discovered_by_id.items():
        if dyn_id not in seen_ids:
            merged.append(dyn_item)
            seen_ids.add(dyn_id)

    result["models"] = merged
    return result


def _default_node_models_list() -> List[Dict[str, str]]:
    return [
        {
            "id": "gemini-web-4-argon",
            "label": "4 Argon",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-4-argon"]["default_hex"],
        },
        {
            "id": "gemini-web-3.1-pro",
            "label": "3.1 Pro",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-3.1-pro"]["default_hex"],
        },
        {
            "id": "gemini-web-3.8-flash",
            "label": "3.8 Flash",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-3.8-flash"]["default_hex"],
        },
        {
            "id": "gemini-web-3.5-flash-lite",
            "label": "3.5 Flash-Lite",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-3.5-flash-lite"]["default_hex"],
        },
        {
            "id": "gemini-web-argon",
            "label": "Gemini Argon",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-argon"]["default_hex"],
        },
        {
            "id": "gemini-web-2.5-pro",
            "label": "Gemini 2.5 Pro",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-2.5-pro"]["default_hex"],
        },
        {
            "id": "gemini-web-2.5-flash",
            "label": "Gemini 2.5 Flash",
            "hex_id": GEMINI_WEB_MODELS["gemini-web-2.5-flash"]["default_hex"],
        },
    ]
