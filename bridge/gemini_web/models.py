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
    "gemini-web-argon": "gemini-web-argon",
    "gemini-argon": "gemini-web-argon",
    "gemini-3.0-argon": "gemini-web-argon",
    "gemini-3-argon": "gemini-web-argon",
    "gemini-web-3.0": "gemini-web-argon",
    "gemini-web-pro": "gemini-web-2.5-pro",
    "gemini-web-2.5-pro": "gemini-web-2.5-pro",
    "gemini-web-flash": "gemini-web-2.5-flash",
    "gemini-web-2.5-flash": "gemini-web-2.5-flash",
    "gemini-web-default": "gemini-web-default",
    "gemini-web": "gemini-web-argon",
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
    """Normalize any model identifier into a canonical GEMINI_WEB_MODELS key."""
    if not model_name:
        return "gemini-web-argon"
    norm = model_name.strip().lower()
    if "/" in norm:
        norm = norm.split("/", 1)[1]
    if norm in GEMINI_WEB_ALIASES:
        return GEMINI_WEB_ALIASES[norm]
    # Map standard Gemini models for web_first or hybrid_failover modes
    if "argon" in norm or "3.8-pro" in norm or "3-pro" in norm or "3.1-pro" in norm or "3.7-pro" in norm:
        return "gemini-web-argon"
    if "pro" in norm:
        return "gemini-web-2.5-pro"
    if "flash" in norm or "lite" in norm:
        return "gemini-web-2.5-flash"
    return "gemini-web-argon"


def resolve_web_model_family(model_name: str) -> str:
    """Resolve model into quota bucket family: 'argon', 'pro', or 'flash'."""
    canonical = resolve_gemini_web_model(model_name)
    meta = GEMINI_WEB_MODELS.get(canonical, {})
    return str(meta.get("family") or "argon")


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
        spec = GEMINI_WEB_MODELS.get(canonical, GEMINI_WEB_MODELS["gemini-web-argon"])
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

    # 2. Detect tier (Ultra / Pro / Advanced / Argon)
    html_lower = html.lower()
    if "gemini ultra" in html_lower or "google ai ultra" in html_lower:
        result["detected_tier"] = "ultra"
    elif (
        "gemini argon" in html_lower
        or "gemini advanced" in html_lower
        or "google one ai" in html_lower
        or "google ai pro" in html_lower
        or "2.5 pro" in html_lower
    ):
        result["detected_tier"] = "pro"

    # 3. Scrape [hex_id, display_name] pairs from inline JSON structures
    # In Bard web responses, model descriptors appear near 16-char lowercase hex strings
    discovered_by_id: Dict[str, Dict[str, str]] = {}
    pair_pattern = re.compile(
        r'\["([0-9a-f]{16})"\s*,\s*"([^"]{2,48})"',
        re.IGNORECASE,
    )
    for m in pair_pattern.finditer(html):
        hex_id = m.group(1).lower()
        label = m.group(2).strip()
        label_lower = label.lower()
        if "argon" in label_lower or "3.0" in label_lower or "ultra" in label_lower:
            discovered_by_id["gemini-web-argon"] = {
                "id": "gemini-web-argon",
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
        elif "flash" in label_lower:
            discovered_by_id["gemini-web-2.5-flash"] = {
                "id": "gemini-web-2.5-flash",
                "label": label,
                "hex_id": hex_id,
            }

    # Merge discovered models with baseline defaults so all 3 primary web models are always available
    merged: List[Dict[str, str]] = []
    for base_item in _default_node_models_list():
        m_id = base_item["id"]
        if m_id in discovered_by_id:
            merged.append(discovered_by_id[m_id])
        else:
            merged.append(base_item)

    result["models"] = merged
    return result


def _default_node_models_list() -> List[Dict[str, str]]:
    return [
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
