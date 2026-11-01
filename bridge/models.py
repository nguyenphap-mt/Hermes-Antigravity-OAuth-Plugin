"""Dynamic Model Discovery & Quota Tracking for Antigravity Code Assist.

Discovers live LLM models, capabilities, and quotas from Google Code Assist backend:
- https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels
- https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary
- Caches locally in ~/.hermes/auth/antigravity_models_cache.json with TTL (3600s).
- Fallback to static baseline models if offline or unauthenticated.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from tools.antigravity_bridge.auth import (
        AntigravityAuthManager,
        AntigravityCredentials,
        get_hermes_dir,
    )
except ImportError:
    from .auth import (
        AntigravityAuthManager,
        AntigravityCredentials,
        get_hermes_dir,
    )

logger = logging.getLogger(__name__)

# Endpoints
# Production Google Code Assist endpoints (matches Antigravity IDE)
MODELS_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
FALLBACK_MODELS_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
QUOTA_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
FALLBACK_QUOTA_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"

DEFAULT_CACHE_TTL_SECONDS = 3600.0  # 1 hour
DEFAULT_PROJECT_ID = "aicode-consumers"

# Direct mapping for legacy / sunset / alias model identifiers to verified live Code Assist backend models
BACKEND_MODEL_ALIASES: Dict[str, str] = {
    # Gemini 3.7 family -> Gemini 3.8
    "gemini-3.7-flash-low": "gemini-3.8-flash-low",
    "gemini-3.7-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.7-flash-high": "gemini-3.8-flash-high",
    "gemini-3.7-flash-tiered": "gemini-3.8-flash-tiered",
    "gemini-3.7-flash": "gemini-3.8-flash-high",
    "gemini-3.7": "gemini-3.8-flash-high",

    # Gemini 3.6 family -> Gemini 3.8
    "gemini-3.6-flash-low": "gemini-3.8-flash-low",
    "gemini-3.6-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.6-flash-high": "gemini-3.8-flash-high",
    "gemini-3.6-flash-tiered": "gemini-3.8-flash-tiered",
    "gemini-3.6-flash": "gemini-3.8-flash-high",

    # Gemini 3.5 family
    "gemini-3.5-flash-low": "gemini-3.8-flash-low",
    "gemini-3.5-flash-extra-low": "gemini-3.8-flash-low",
    "gemini-3.5-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.5-flash-high": "gemini-3.8-flash-high",
    "gemini-3.5-flash": "gemini-3.8-flash-high",
    "gemini-3.5-flash-lite": "gemini-3.8-flash-low",

    # Gemini 3.1 Pro / Pro agent / 2.5 Pro -> Gemini 3.8 Flash High
    "gemini-3.1-pro-high": "gemini-3.8-flash-high",
    "gemini-3.1-pro-low": "gemini-3.8-flash-low",
    "gemini-pro-agent": "gemini-3.8-flash-high",
    "gemini-2.5-pro": "gemini-3.8-flash-high",
    "gemini-pro": "gemini-3.8-flash-high",

    # Claude aliases
    "claude-3-7-sonnet": "claude-sonnet-4-6",
    "claude-3.7-sonnet": "claude-sonnet-4-6",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "claude-3-7-opus": "claude-opus-4-6-thinking",
    "claude-3.7-opus": "claude-opus-4-6-thinking",
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-opus": "claude-opus-4-6-thinking",

    # GPT OSS aliases
    "gpt-oss": "gpt-oss-120b-medium",
    "gpt-oss-120b": "gpt-oss-120b-medium",

    # Gemini 4 Argon (Code Assist)
    "gemini-4-argon": "gemini-4-argon-high",
    "gemini-4-argon-high": "gemini-4-argon-high",
    "gemini-4-argon-medium": "gemini-4-argon-medium",
    "gemini-4-argon-low": "gemini-4-argon-low",

    # Gemini Web App (gemini.google.com/app) models & thinking levels
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
    "gemini-web-argon": "gemini-web-argon",
    "gemini-argon": "gemini-web-4-argon",
    "gemini-3.0-argon": "gemini-web-argon",
    "gemini-web-2.5-pro": "gemini-web-2.5-pro",
    "gemini-web-pro": "gemini-web-3.1-pro",
    "gemini-web-2.5-flash": "gemini-web-2.5-flash",
    "gemini-web-flash": "gemini-web-3.8-flash",
    "gemini-web-flash-lite": "gemini-web-3.5-flash-lite",
    "gemini-web-default": "gemini-web-default",
}

# Curated static baseline fallback models (used if offline / unauthenticated)
BASELINE_MODELS: Dict[str, Dict[str, Any]] = {
    "gemini-3-flash-agent": {
        "displayName": "Gemini 3.5 Flash (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M84",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "claude-opus-4-6-thinking": {
        "displayName": "Claude Opus 4.6 (Thinking)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1024,
        "minThinkingBudget": 32,
        "maxTokens": 250000,
        "maxOutputTokens": 64000,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M26",
        "apiProvider": "API_PROVIDER_ANTHROPIC_VERTEX"
    },
    "gemini-3.8-flash-high": {
        "displayName": "Gemini 3.8 Flash (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M318",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.8-flash-medium": {
        "displayName": "Gemini 3.8 Flash (Medium)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M319",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.6-flash-tiered": {
        "displayName": "Gemini 3.6 Flash Tiered",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M196",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gpt-oss-120b-medium": {
        "displayName": "GPT-OSS 120B (Medium)",
        "supportsImages": False,
        "supportsThinking": True,
        "thinkingBudget": 8192,
        "minThinkingBudget": 32,
        "maxTokens": 131072,
        "maxOutputTokens": 32768,
        "recommended": True,
        "model": "MODEL_OPENAI_GPT_OSS_120B_MEDIUM",
        "apiProvider": "API_PROVIDER_OPENAI_VERTEX"
    },
    "chat_20706": {
        "displayName": "Chat_20706",
        "supportsImages": False,
        "supportsThinking": False,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 16384,
        "maxOutputTokens": 65536,
        "recommended": False,
        "model": "MODEL_CHAT_20706",
        "apiProvider": "API_PROVIDER_INTERNAL"
    },
    "gemini-3.5-flash-lite": {
        "displayName": "Gemini 3.5 Flash Lite",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M198",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-2.5-pro": {
        "displayName": "Gemini 2.5 Pro",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1024,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_GOOGLE_GEMINI_2_5_PRO",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.6-flash-low": {
        "displayName": "Gemini 3.6 Flash (Low)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M73",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.8-flash-low": {
        "displayName": "Gemini 3.8 Flash (Low)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M320",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.1-pro-high": {
        "displayName": "Gemini 3.1 Pro (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 10001,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M37",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.7-flash-tiered": {
        "displayName": "Gemini 3.7 Flash Tiered",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M301",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.7-flash-medium": {
        "displayName": "Gemini 3.7 Flash (Medium)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M299",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "claude-sonnet-4-6": {
        "displayName": "Claude Sonnet 4.6 (Thinking)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1024,
        "minThinkingBudget": 32,
        "maxTokens": 250000,
        "maxOutputTokens": 64000,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M35",
        "apiProvider": "API_PROVIDER_ANTHROPIC_VERTEX"
    },
    "gemini-3.1-flash-lite": {
        "displayName": "Gemini 3.1 Flash Lite",
        "supportsImages": False,
        "supportsThinking": False,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": False,
        "model": "MODEL_PLACEHOLDER_M50",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-2.5-flash-lite": {
        "displayName": "Gemini 2.5 Flash Lite",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_GOOGLE_GEMINI_2_5_FLASH_LITE",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.7-flash-high": {
        "displayName": "Gemini 3.7 Flash (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M298",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-pro-agent": {
        "displayName": "Gemini 3.1 Pro (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M16",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.6-flash-high": {
        "displayName": "Gemini 3.6 Flash (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M71",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "tab_jump_flash_lite_preview": {
        "displayName": "Tab_Jump_Flash_Lite_Preview",
        "supportsImages": False,
        "supportsThinking": False,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 16384,
        "maxOutputTokens": 4096,
        "recommended": False,
        "model": "MODEL_PLACEHOLDER_M28",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.6-flash-medium": {
        "displayName": "Gemini 3.6 Flash (Medium)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M72",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3-flash": {
        "displayName": "Gemini 3 Flash",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M18",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.7-flash-low": {
        "displayName": "Gemini 3.7 Flash (Low)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M300",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "chat_23310": {
        "displayName": "Chat_23310",
        "supportsImages": False,
        "supportsThinking": False,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 32768,
        "maxOutputTokens": 65536,
        "recommended": False,
        "model": "MODEL_CHAT_23310",
        "apiProvider": "API_PROVIDER_INTERNAL"
    },
    "gemini-2.5-flash-thinking": {
        "displayName": "Gemini 2.5 Flash (Thinking)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_GOOGLE_GEMINI_2_5_FLASH_THINKING",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-2.5-flash": {
        "displayName": "Gemini 2.5 Flash",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_GOOGLE_GEMINI_2_5_FLASH",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.1-flash-image": {
        "displayName": "Gemini 3.1 Flash Image",
        "supportsImages": False,
        "supportsThinking": False,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": False,
        "model": "MODEL_PLACEHOLDER_M21",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.8-flash-tiered": {
        "displayName": "Gemini 3.8 Flash Tiered",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M322",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.1-pro-low": {
        "displayName": "Gemini 3.1 Pro (Low)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1001,
        "minThinkingBudget": 128,
        "maxTokens": 1048576,
        "maxOutputTokens": 65535,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M36",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "tab_flash_lite_preview": {
        "displayName": "Tab_Flash_Lite_Preview",
        "supportsImages": False,
        "supportsThinking": False,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 16384,
        "maxOutputTokens": 4096,
        "recommended": False,
        "model": "MODEL_PLACEHOLDER_M19",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.5-flash-low": {
        "displayName": "Gemini 3.5 Flash (Medium)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M20",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-3.5-flash-extra-low": {
        "displayName": "Gemini 3.5 Flash (Low)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M187",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-4-argon-high": {
        "displayName": "Gemini 4 Argon (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M417",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-4-argon-medium": {
        "displayName": "Gemini 4 Argon (Medium)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M418",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-4-argon-low": {
        "displayName": "Gemini 4 Argon (Low)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M419",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI"
    },
    "gemini-web-4-argon": {
        "displayName": "Gemini 4 Argon (Web App — Nhiệm vụ phức tạp)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-4-argon-high": {
        "displayName": "Gemini 4 Argon High (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON_HIGH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-4-argon-medium": {
        "displayName": "Gemini 4 Argon Medium (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON_MEDIUM",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-4-argon-low": {
        "displayName": "Gemini 4 Argon Low (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_4_ARGON_LOW",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.1-pro": {
        "displayName": "Gemini 3.1 Pro (Web App — Suy luận nâng cao)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_31_PRO",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.1-pro-high": {
        "displayName": "Gemini 3.1 Pro High (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_31_PRO_HIGH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.1-pro-low": {
        "displayName": "Gemini 3.1 Pro Low (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_31_PRO_LOW",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.8-flash": {
        "displayName": "Gemini 3.8 Flash (Web App — Trợ giúp toàn diện)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.8-flash-high": {
        "displayName": "Gemini 3.8 Flash High (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH_HIGH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.8-flash-medium": {
        "displayName": "Gemini 3.8 Flash Medium (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH_MEDIUM",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.8-flash-low": {
        "displayName": "Gemini 3.8 Flash Low (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 1000,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_38_FLASH_LOW",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-3.5-flash-lite": {
        "displayName": "Gemini 3.5 Flash-Lite (Web App — Nhanh nhất)",
        "supportsImages": True,
        "supportsThinking": False,
        "thinkingBudget": 0,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_35_FLASH_LITE",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-argon": {
        "displayName": "Gemini Argon (Web App Pro/Ultra)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_ARGON",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-2.5-pro": {
        "displayName": "Gemini 2.5 Pro (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_25_PRO",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    },
    "gemini-web-2.5-flash": {
        "displayName": "Gemini 2.5 Flash (Web App)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": -1,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_GEMINI_WEB_25_FLASH",
        "apiProvider": "API_PROVIDER_GEMINI_WEB"
    }
}


@dataclass
class DiscoveredModel:
    """Standardized representation of a discovered Code Assist model."""
    id: str
    display_name: str
    code_assist_id: str
    max_tokens: int
    max_output_tokens: int
    supports_thinking: bool
    thinking_budget: int
    min_thinking_budget: int
    supports_images: bool
    supports_video: bool
    recommended: bool
    quota_fraction: Optional[float] = None
    reset_time: Optional[str] = None
    provider: str = "antigravity"

    def to_openai_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "antigravity",
            "display_name": self.display_name,
            "max_tokens": self.max_tokens,
            "max_output_tokens": self.max_output_tokens,
            "supports_thinking": self.supports_thinking,
            "thinking_budget": self.thinking_budget,
            "min_thinking_budget": self.min_thinking_budget,
            "supports_images": self.supports_images,
            "supports_video": self.supports_video,
            "recommended": self.recommended,
            "quota_fraction": self.quota_fraction,
            "reset_time": self.reset_time,
            "permission": [],
        }


class ModelDiscoveryManager:
    """Thread-safe manager for dynamic model discovery and quota tracking."""

    def __init__(
        self,
        auth_manager: Optional[AntigravityAuthManager] = None,
        cache_file: Optional[Path] = None,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        is_bridge_server: bool = False,
    ) -> None:
        self.auth_manager = auth_manager or AntigravityAuthManager()
        self.cache_file = cache_file or (get_hermes_dir() / "auth" / "antigravity_models_cache.json")
        self.ttl_seconds = ttl_seconds
        self.is_bridge_server = is_bridge_server
        self._lock = threading.Lock()
        self._memory_cache: Optional[Dict[str, Any]] = None

    def get_cache_path(self) -> Path:
        return self.cache_file

    def _fetch_from_local_bridge(self) -> Optional[Dict[str, Any]]:
        """Attempt to fetch live models from local bridge daemon on port 8100 (only from external CLI/processes)."""
        if (
            os.environ.get("PYTEST_CURRENT_TEST")
            or self.is_bridge_server
            or os.environ.get("ANTIGRAVITY_IN_BRIDGE_SERVER") == "1"
        ):
            return None
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8100/v1/models",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Antigravity-Discovery/1.0",
                    "X-Antigravity-Internal-Probe": "1",
                },
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models_list = data.get("data", [])
                if models_list:
                    res = {}
                    for item in models_list:
                        mid = item.get("id")
                        if mid:
                            res[mid] = {
                                "displayName": item.get("display_name") or mid,
                                "maxTokens": item.get("max_tokens", 1048576),
                                "maxOutputTokens": item.get("max_output_tokens", 65536),
                                "supportsThinking": item.get("supports_thinking", False),
                                "thinkingBudget": item.get("thinking_budget", 2048),
                                "minThinkingBudget": item.get("min_thinking_budget", 32),
                                "supportsImages": item.get("supports_images", False),
                                "supportsVideo": item.get("supports_video", False),
                                "recommended": item.get("recommended", True),
                                "model": mid,
                            }
                    return res
        except Exception:
            pass
        return None

    def _load_cache_from_disk(self) -> Optional[Dict[str, Any]]:
        if not self.cache_file.is_file():
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_at = float(data.get("cached_at", 0))
            if (time.time() - cached_at) < self.ttl_seconds:
                return data
            logger.debug("Model cache expired (age: %.1fs > TTL: %.1fs)", time.time() - cached_at, self.ttl_seconds)
        except Exception as e:
            logger.debug("Failed to read model cache from %s: %s", self.cache_file, e)
        return None

    def _save_cache_to_disk(self, data: Dict[str, Any]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self.cache_file.with_suffix(".tmp")
            data["cached_at"] = time.time()
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_file.replace(self.cache_file)
            self._memory_cache = data
        except Exception as e:
            logger.warning("Failed to save model cache to %s: %s", self.cache_file, e)

    def _resolve_candidate_credentials(self) -> List[Any]:
        """Resolve all valid and available plugin OAuth credentials from primary and multi-account pool."""
        candidates: List[Any] = []
        seen_tokens: set[str] = set()

        try:
            primary = self.auth_manager.resolve_valid_credentials()
            if primary and getattr(primary, "access_token", ""):
                candidates.append(primary)
                seen_tokens.add(primary.access_token)
        except Exception as e:
            logger.debug("Primary credential resolution failed: %s", e)

        auth_file = getattr(self.auth_manager, "auth_file", None)
        if isinstance(auth_file, Path):
            try:
                try:
                    from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
                except ImportError:
                    from bridge.account_pool import AntigravityAccountPoolManager
                pool = AntigravityAccountPoolManager(storage_path=auth_file)
                for acc in pool.list_accounts():
                    if not acc.email or not acc.is_available:
                        continue
                    try:
                        c = self.auth_manager.resolve_valid_credentials(bearer_token=acc.email)
                        tok = getattr(c, "access_token", "")
                        if c and tok and tok not in seen_tokens:
                            candidates.append(c)
                            seen_tokens.add(tok)
                    except Exception:
                        continue
            except Exception as e:
                logger.debug("Pool credential enumeration failed: %s", e)

        return candidates

    def _set_negative_memory_cache(self, models_dict: Dict[str, Any]) -> None:
        """Cache fallback models in RAM for up to 5 minutes to prevent tight retry loops."""
        neg_ttl = min(float(self.ttl_seconds), 300.0)
        with self._lock:
            self._memory_cache = {
                "models": models_dict,
                "cached_at": time.time() - (float(self.ttl_seconds) - neg_ttl),
            }

    @staticmethod
    def _decode_response_bytes(resp: Any) -> str:
        raw_bytes = resp.read()
        if isinstance(raw_bytes, bytes):
            if raw_bytes[:2] == b"\x1f\x8b":
                import gzip
                raw_bytes = gzip.decompress(raw_bytes)
            return raw_bytes.decode("utf-8")
        return str(raw_bytes)

    def fetch_models(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch models dynamically from Google Code Assist API or return cached."""
        with self._lock:
            if not force_refresh:
                if self._memory_cache and (time.time() - self._memory_cache.get("cached_at", 0) < self.ttl_seconds):
                    return self._memory_cache.get("models", {})
                disk_cache = self._load_cache_from_disk()
                if disk_cache:
                    self._memory_cache = disk_cache
                    return disk_cache.get("models", {})

        candidate_creds = self._resolve_candidate_credentials()
        if not candidate_creds:
            local_models = self._fetch_from_local_bridge()
            if local_models:
                self._set_negative_memory_cache(local_models)
                return local_models
            fallback = self._fallback_models()
            self._set_negative_memory_cache(fallback)
            return fallback

        endpoints = [MODELS_ENDPOINT, FALLBACK_MODELS_ENDPOINT]
        raw_models: Dict[str, Any] = {}
        successful_pid = ""
        successful_creds = candidate_creds[0]

        for creds in candidate_creds:
            eff_pid = getattr(creds, "effective_project_id", None)
            raw_pid = getattr(creds, "project_id", None)
            candidate_projects: List[str] = []
            if isinstance(eff_pid, str) and eff_pid.strip() and eff_pid.strip() != DEFAULT_PROJECT_ID:
                candidate_projects.append(eff_pid.strip())
            if (
                isinstance(raw_pid, str)
                and raw_pid.strip()
                and raw_pid.strip() != DEFAULT_PROJECT_ID
                and raw_pid.strip() not in candidate_projects
            ):
                candidate_projects.append(raw_pid.strip())
            if "" not in candidate_projects:
                candidate_projects.append("")

            for pid in candidate_projects:
                payload_bytes = json.dumps({"project": pid}).encode("utf-8")
                try:
                    from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
                    headers = AntigravityFingerprint.build_headers(getattr(creds, "access_token", ""), project_id=pid)
                except ImportError:
                    try:
                        from bridge.fingerprint import AntigravityFingerprint
                        headers = AntigravityFingerprint.build_headers(getattr(creds, "access_token", ""), project_id=pid)
                    except Exception:
                        headers = {
                            "Content-Type": "application/json",
                            "Accept-Encoding": "gzip",
                            "Authorization": f"Bearer {getattr(creds, 'access_token', '')}",
                            "User-Agent": "antigravity/2.23.1 (aidev_client; os_type=windows; arch=amd64; cl=998881661)",
                            "X-Goog-Api-Client": "gl-go/1.24.0 gccl/2.23.1 antigravity/2.23.1",
                        }

                for ep in endpoints:
                    try:
                        req = urllib.request.Request(ep, data=payload_bytes, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=12.0) as resp:
                            resp_data = json.loads(self._decode_response_bytes(resp))
                            raw_models = resp_data.get("models", {})
                            if raw_models:
                                successful_pid = pid
                                successful_creds = creds
                                logger.info(
                                    "Successfully discovered %d models from %s (project: %s, account: %s)",
                                    len(raw_models), ep, pid, getattr(creds, "email", ""),
                                )
                                break
                    except Exception as e:
                        logger.debug("Failed querying models endpoint %s with project %s: %s", ep, pid, e)
                if raw_models:
                    break
            if raw_models:
                break

        if not raw_models:
            local_models = self._fetch_from_local_bridge()
            if local_models:
                self._set_negative_memory_cache(local_models)
                return local_models
            logger.warning("Failed to query live models from Code Assist; using baseline fallback.")
            fallback = self._fallback_models()
            self._set_negative_memory_cache(fallback)
            return fallback

        cache_data = {
            "models": raw_models,
            "project_id": successful_pid,
            "email": getattr(successful_creds, "email", ""),
        }
        with self._lock:
            self._save_cache_to_disk(cache_data)
        return raw_models

    def fetch_quota_summary(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch quota summary from retrieveUserQuotaSummary across available accounts."""
        candidate_creds = self._resolve_candidate_credentials()
        if not candidate_creds:
            return {}

        for creds in candidate_creds:
            eff_pid = getattr(creds, "effective_project_id", None)
            raw_pid = getattr(creds, "project_id", None)
            candidate_projects: List[str] = []
            if isinstance(eff_pid, str) and eff_pid.strip() and eff_pid.strip() != DEFAULT_PROJECT_ID:
                candidate_projects.append(eff_pid.strip())
            if (
                isinstance(raw_pid, str)
                and raw_pid.strip()
                and raw_pid.strip() != DEFAULT_PROJECT_ID
                and raw_pid.strip() not in candidate_projects
            ):
                candidate_projects.append(raw_pid.strip())
            if "" not in candidate_projects:
                candidate_projects.append("")

            for pid in candidate_projects:
                payload_bytes = json.dumps({"project": pid}).encode("utf-8")
                try:
                    from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
                    headers = AntigravityFingerprint.build_headers(getattr(creds, "access_token", ""), project_id=pid)
                except ImportError:
                    try:
                        from bridge.fingerprint import AntigravityFingerprint
                        headers = AntigravityFingerprint.build_headers(getattr(creds, "access_token", ""), project_id=pid)
                    except Exception:
                        headers = {
                            "Content-Type": "application/json",
                            "Accept-Encoding": "gzip",
                            "Authorization": f"Bearer {getattr(creds, 'access_token', '')}",
                            "User-Agent": "antigravity/2.23.1 (aidev_client; os_type=windows; arch=amd64; cl=998881661)",
                            "X-Goog-Api-Client": "gl-go/1.24.0 gccl/2.23.1 antigravity/2.23.1",
                        }

                for ep in [QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT]:
                    try:
                        req = urllib.request.Request(ep, data=payload_bytes, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=10.0) as resp:
                            res = json.loads(self._decode_response_bytes(resp))
                            if res:
                                return res
                    except Exception as e:
                        logger.debug("Failed querying quota endpoint %s with project %s: %s", ep, pid, e)
        return {}

    def _fallback_models(self) -> Dict[str, Any]:
        if self._memory_cache and self._memory_cache.get("models"):
            return self._memory_cache["models"]
        # Try expired cache from disk
        if self.cache_file.is_file():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("models"):
                    return data["models"]
            except Exception:
                pass
        return BASELINE_MODELS

    def get_discovered_models(self, force_refresh: bool = False) -> List[DiscoveredModel]:
        """Return parsed DiscoveredModel objects."""
        raw_models = {
            k: v for k, v in (self.fetch_models(force_refresh=force_refresh) or {}).items()
            if not str(k).endswith("-disabled")
        }
        if isinstance(getattr(self.auth_manager, "auth_file", None), Path):
            # 1. Dynamically synthesize gemini-web-* models from live Google API (fetchAvailableModels)
            live_snapshot = list(raw_models.items())
            for live_id, live_meta in live_snapshot:
                if not isinstance(live_meta, dict) or not live_id.startswith("gemini-"):
                    continue
                if live_id.startswith("gemini-web-") or live_id.endswith(("-image", "-disabled")) or "customtools" in live_id:
                    continue
                suffix = live_id[len("gemini-"):]
                web_id = f"gemini-web-{suffix}"
                live_disp = str(live_meta.get("displayName") or suffix.replace("-", " ").title()).strip()
                if web_id not in raw_models:
                    raw_models[web_id] = {
                        **live_meta,
                        "displayName": f"{live_disp} (Web App)" if "(Web App)" not in live_disp else live_disp,
                        "model": f"MODEL_{web_id.upper().replace('-', '_').replace('.', '_')}",
                        "apiProvider": "API_PROVIDER_GEMINI_WEB",
                    }
                # Also synthesize base model alias without -high/-medium/-low if not present
                for tier_suffix in ("-high", "-medium", "-low"):
                    if suffix.endswith(tier_suffix):
                        base_suffix = suffix[: -len(tier_suffix)]
                        base_web_id = f"gemini-web-{base_suffix}"
                        if base_web_id not in raw_models:
                            base_disp = re.sub(r"\s*\((?:High|Medium|Low)\)\s*$", "", live_disp, flags=re.IGNORECASE).strip()
                            raw_models[base_web_id] = {
                                **live_meta,
                                "displayName": f"{base_disp} (Web App)" if "(Web App)" not in base_disp else base_disp,
                                "model": f"MODEL_{base_web_id.upper().replace('-', '_').replace('.', '_')}",
                                "apiProvider": "API_PROVIDER_GEMINI_WEB",
                            }
                        break

            # 2. Merge baseline gemini-web-* models (ensuring Web App-exclusive models like 3.1 Pro are always present)
            for k, v in BASELINE_MODELS.items():
                if k.startswith("gemini-web-") and k not in raw_models:
                    raw_models[k] = v

            # 3. Merge live-scraped models from gemini_web_pool.json (WIZ_global_data HTML scraper)
            try:
                pool_file = get_hermes_dir() / "gemini_web_pool.json"
                if pool_file.is_file():
                    with open(pool_file, "r", encoding="utf-8") as pf:
                        pdata = json.load(pf)
                    for node in (pdata.get("nodes") or []) if isinstance(pdata, dict) else []:
                        for m_item in (node.get("available_models") or []) if isinstance(node, dict) else []:
                            if isinstance(m_item, dict) and m_item.get("id"):
                                mid = str(m_item["id"]).strip()
                                mlabel = str(m_item.get("display_name") or m_item.get("label") or mid).strip()
                                if mid.startswith("gemini-web-") and mid not in raw_models:
                                    raw_models[mid] = {
                                        "displayName": f"Gemini {mlabel} (Web App)" if not mlabel.lower().startswith("gemini") else mlabel,
                                        "supportsImages": True,
                                        "supportsThinking": "lite" not in mid,
                                        "thinkingBudget": -1,
                                        "minThinkingBudget": 32,
                                        "maxTokens": 1048576,
                                        "maxOutputTokens": 65536,
                                        "recommended": True,
                                        "model": f"MODEL_{mid.upper().replace('-', '_').replace('.', '_')}",
                                        "apiProvider": "API_PROVIDER_GEMINI_WEB",
                                    }
            except Exception:
                pass
        models_list: List[DiscoveredModel] = []

        for model_id, m in raw_models.items():
            if not isinstance(m, dict):
                continue
            disp = m.get("displayName")
            if not disp or disp == "None":
                disp = BASELINE_MODELS.get(model_id, {}).get("displayName") or model_id.replace("-", " ").title()
            code_assist_id = m.get("model") or model_id
            max_tok = int(m.get("maxTokens") or 1048576)
            max_out = int(m.get("maxOutputTokens") or 65536)
            sup_thinking = bool(m.get("supportsThinking", False))
            thinking_budget = int(m.get("thinkingBudget") or 2048)
            min_thinking = int(m.get("minThinkingBudget") or 32)
            sup_images = bool(m.get("supportsImages", False))
            sup_video = bool(m.get("supportsVideo", False))
            rec = bool(m.get("recommended", False))

            quota_fraction = None
            reset_time = None
            if isinstance(m.get("quotaInfo"), dict):
                quota_fraction = m["quotaInfo"].get("remainingFraction")
                reset_time = m["quotaInfo"].get("resetTime")

            models_list.append(
                DiscoveredModel(
                    id=model_id,
                    display_name=disp,
                    code_assist_id=code_assist_id,
                    max_tokens=max_tok,
                    max_output_tokens=max_out,
                    supports_thinking=sup_thinking,
                    thinking_budget=thinking_budget,
                    min_thinking_budget=min_thinking,
                    supports_images=sup_images,
                    supports_video=sup_video,
                    recommended=rec,
                    quota_fraction=quota_fraction,
                    reset_time=reset_time,
                )
            )

        # Sort: recommended first, then alphabetically
        models_list.sort(key=lambda x: (not x.recommended, x.id))
        return models_list

    def list_openai_models(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Return model list in OpenAI /v1/models compatible structure."""
        return [m.to_openai_dict() for m in self.get_discovered_models(force_refresh=force_refresh)]

    def get_model_ids(self, force_refresh: bool = False) -> List[str]:
        """Return list of string IDs for picker menus."""
        return [m.id for m in self.get_discovered_models(force_refresh=force_refresh)]

    def resolve_model(self, requested_model: str) -> Tuple[str, Dict[str, Any]]:
        """Map user-requested model identifier to live internal Code Assist identifier.

        Returns:
            Tuple[code_assist_model_name, metadata_dict]
        """
        if not requested_model:
            return ("gemini-3.8-flash-high", {})

        norm = requested_model.lower().strip()
        if "/" in norm:
            norm = norm.split("/", 1)[1]

        models = self.get_discovered_models(force_refresh=False)
        model_map = {m.id.lower(): m for m in models}

        # 1. Alias / Sunset mapping to live backend model
        target_norm = BACKEND_MODEL_ALIASES.get(norm, norm)
        if target_norm in model_map:
            target = model_map[target_norm]
            return (target.id, target.to_openai_dict())

        # 2. Exact match on model ID (if not an alias)
        if norm in model_map:
            target = model_map[norm]
            return (target.id, target.to_openai_dict())

        # 2b. On cache miss for an unknown model, attempt a live refresh from Antigravity IDE
        last_refresh = getattr(self, "_last_miss_refresh_ts", 0.0)
        if (time.time() - last_refresh) > 60.0 and target_norm == norm:
            self._last_miss_refresh_ts = time.time()
            models = self.get_discovered_models(force_refresh=True)
            model_map = {m.id.lower(): m for m in models}
            if norm in model_map:
                target = model_map[norm]
                return (target.id, target.to_openai_dict())

        # 3. Match by display name substring or slug alias
        alias_rules = [
            ("gemini-3.8-flash", ["gemini-3.8-flash-tiered", "gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low"]),
            ("gemini-3.8", ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-tiered", "gemini-3.8-flash-low"]),
            ("gemini-3.7-flash", ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low", "gemini-3.8-flash-tiered"]),
            ("gemini-3.7", ["gemini-3.8-flash-high", "gemini-3.8-flash-medium"]),
            ("gemini-3.6-flash", ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low"]),
            ("gemini-3.5-flash", ["gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high"]),
            ("gemini-3.1-pro", ["gemini-3.8-flash-high", "gemini-3.8-flash-low"]),
            ("gemini-pro", ["gemini-3.8-flash-high"]),
            ("gemini-flash", ["gemini-3.8-flash-high", "gemini-3.8-flash-tiered", "gemini-3-flash-agent", "gemini-3-flash"]),
            ("gemini-2.5-flash", ["gemini-2.5-flash", "gemini-3.8-flash-low"]),
            ("gemini-2.5-pro", ["gemini-2.5-pro", "gemini-3.8-flash-high"]),
            ("claude-sonnet-4-6", ["claude-sonnet-4-6"]),
            ("claude-sonnet-4.6", ["claude-sonnet-4-6"]),
            ("claude-3-7-sonnet", ["claude-sonnet-4-6"]),
            ("claude-3.7-sonnet", ["claude-sonnet-4-6"]),
            ("claude-opus-4-6", ["claude-opus-4-6-thinking", "claude-sonnet-4-6"]),
            ("claude-opus", ["claude-opus-4-6-thinking", "claude-sonnet-4-6"]),
            ("claude-sonnet", ["claude-sonnet-4-6"]),
            ("gpt-oss", ["gpt-oss-120b-medium"]),
            ("gpt-oss-120b", ["gpt-oss-120b-medium"]),
        ]

        for trigger, candidates in alias_rules:
            if norm == trigger or norm.startswith(trigger):
                for cand in candidates:
                    if cand.lower() in model_map:
                        target = model_map[cand.lower()]
                        return (target.id, target.to_openai_dict())

        # 4. Fuzzy search in model IDs
        for mid, m in model_map.items():
            if norm in mid:
                return (m.id, m.to_openai_dict())

        # Fallback to recommended or first available
        for m in models:
            if "3.8" in m.id and "flash" in m.id:
                return (m.id, m.to_openai_dict())

        for m in models:
            if "flash" in m.id:
                return (m.id, m.to_openai_dict())

        if models:
            return (models[0].id, models[0].to_openai_dict())

        return ("gemini-3.8-flash-high", {})
