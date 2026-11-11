"""Gemini Web App (`gemini.google.com/app`) Quota Bridge & Dedicated Web Pool Management."""

from .browser_login import GeminiWebBrowserLoginManager, get_shared_browser_login_manager
from .client import GeminiWebClient, parse_bard_stream_generate_response
from .models import (
    GEMINI_WEB_ALIASES,
    GEMINI_WEB_MODELS,
    build_model_selector_header,
    is_explicit_gemini_web_model,
    resolve_gemini_web_model,
    resolve_web_model_family,
    scrape_models_and_tier_from_html,
)
from .pool_manager import GeminiWebNode, GeminiWebPoolManager
from .session_manager import GeminiWebSessionManager, parse_flexible_cookie_input
from .tool_adapter import GeminiWebToolAdapter

__all__ = [
    "GEMINI_WEB_ALIASES",
    "GEMINI_WEB_MODELS",
    "GeminiWebBrowserLoginManager",
    "GeminiWebClient",
    "GeminiWebNode",
    "GeminiWebPoolManager",
    "GeminiWebSessionManager",
    "GeminiWebToolAdapter",
    "build_model_selector_header",
    "get_shared_browser_login_manager",
    "is_explicit_gemini_web_model",
    "parse_bard_stream_generate_response",
    "parse_flexible_cookie_input",
    "resolve_gemini_web_model",
    "resolve_web_model_family",
    "scrape_models_and_tier_from_html",
]
