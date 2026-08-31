"""Antigravity Local OAuth Bridge for Hermes Agent.

Provides a local OpenAI-compatible HTTP daemon that simulates Antigravity IDE/CLI
client headers, manages Google OAuth 2.0 PKCE authentication, translates OpenAI
chat payloads into Gemini/Code Assist generateContent requests, and surfaces
models to Hermes.
"""

from __future__ import annotations

from .auth import (
    AntigravityAuthManager,
    AntigravityCredentials,
)
from .client import (
    AntigravityClient,
    ANTIGRAVITY_SUPPORTED_MODELS,
)
from .server import (
    AntigravityBridgeServer,
    run_server,
)

__all__ = [
    "AntigravityAuthManager",
    "AntigravityCredentials",
    "AntigravityClient",
    "ANTIGRAVITY_SUPPORTED_MODELS",
    "AntigravityBridgeServer",
    "run_server",
]
