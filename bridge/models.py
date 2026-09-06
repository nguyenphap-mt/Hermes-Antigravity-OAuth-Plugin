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
MODELS_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
FALLBACK_MODELS_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
QUOTA_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
FALLBACK_QUOTA_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"

DEFAULT_CACHE_TTL_SECONDS = 3600.0  # 1 hour
DEFAULT_PROJECT_ID = "aicode-consumers"

# Curated static baseline fallback models (used if offline / unauthenticated)
BASELINE_MODELS: Dict[str, Dict[str, Any]] = {
    "gemini-3.7-flash-tiered": {
        "displayName": "Gemini 3.7 Flash Tiered",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "MODEL_PLACEHOLDER_M196",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
        "tagTitle": "Fast & Smart",
    },
    "gemini-3.6-flash-high": {
        "displayName": "Gemini 3.6 Flash (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4096,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "gemini-3.6-flash-high",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
    },
    "gemini-3.6-flash-medium": {
        "displayName": "Gemini 3.6 Flash (Medium)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "gemini-3.6-flash-medium",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
    },
    "gemini-3.1-pro-high": {
        "displayName": "Gemini 3.1 Pro (High)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4096,
        "minThinkingBudget": 32,
        "maxTokens": 1048576,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "gemini-3.1-pro-high",
        "apiProvider": "API_PROVIDER_GOOGLE_GEMINI",
    },
    "claude-sonnet-4-6": {
        "displayName": "Claude Sonnet 4.6 (Thinking)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 4096,
        "minThinkingBudget": 100,
        "maxTokens": 250000,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "claude-sonnet-4-6",
        "apiProvider": "API_PROVIDER_ANTHROPIC",
    },
    "claude-opus-4-6-thinking": {
        "displayName": "Claude Opus 4.6 (Thinking)",
        "supportsImages": True,
        "supportsThinking": True,
        "thinkingBudget": 8192,
        "minThinkingBudget": 100,
        "maxTokens": 250000,
        "maxOutputTokens": 65536,
        "recommended": True,
        "model": "claude-opus-4-6-thinking",
        "apiProvider": "API_PROVIDER_ANTHROPIC",
    },
    "gpt-oss-120b-medium": {
        "displayName": "GPT-OSS 120B (Medium)",
        "supportsImages": False,
        "supportsThinking": True,
        "thinkingBudget": 2048,
        "minThinkingBudget": 32,
        "maxTokens": 131072,
        "maxOutputTokens": 16384,
        "recommended": True,
        "model": "gpt-oss-120b-medium",
        "apiProvider": "API_PROVIDER_OPENAI_COMPATIBLE",
    },
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
    ) -> None:
        self.auth_manager = auth_manager or AntigravityAuthManager()
        self.cache_file = cache_file or (get_hermes_dir() / "auth" / "antigravity_models_cache.json")
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._memory_cache: Optional[Dict[str, Any]] = None

    def get_cache_path(self) -> Path:
        return self.cache_file

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

        # Resolve credentials
        try:
            creds = self.auth_manager.resolve_valid_credentials()
        except Exception as e:
            logger.debug("Could not resolve credentials for model discovery: %s", e)
            return self._fallback_models()

        raw_pid = getattr(creds, "project_id", None)
        candidate_projects: List[str] = []
        if isinstance(raw_pid, str) and raw_pid.strip():
            candidate_projects.append(raw_pid.strip())
        if DEFAULT_PROJECT_ID not in candidate_projects:
            candidate_projects.append(DEFAULT_PROJECT_ID)

        endpoints = [MODELS_ENDPOINT, FALLBACK_MODELS_ENDPOINT]
        raw_models: Dict[str, Any] = {}
        successful_pid = DEFAULT_PROJECT_ID

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
                        "Authorization": f"Bearer {getattr(creds, 'access_token', '')}",
                        "User-Agent": "Antigravity/2.11.0 (Windows NT 10.0; Win64; x64) Code-Assist/2026.03.0",
                        "X-Goog-Api-Client": "gl-go/1.24.0 gccl/2.11.0 antigravity/2.11.0",
                        "Client-Metadata": json.dumps({
                            "ideType": "ANTIGRAVITY",
                            "platform": "PLATFORM_WINDOWS",
                            "pluginType": "GEMINI",
                            "applicationVersion": "2.11.0",
                        }, separators=(",", ":")),
                    }

            for ep in endpoints:
                try:
                    req = urllib.request.Request(ep, data=payload_bytes, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=12.0) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        raw_models = resp_data.get("models", {})
                        if raw_models:
                            successful_pid = pid
                            logger.info("Successfully discovered %d models from %s (project: %s)", len(raw_models), ep, pid)
                            break
                except Exception as e:
                    logger.debug("Failed querying models endpoint %s with project %s: %s", ep, pid, e)
            if raw_models:
                break

        if not raw_models:
            logger.warning("Failed to query live models from Code Assist; using baseline fallback.")
            return self._fallback_models()

        cache_data = {
            "models": raw_models,
            "project_id": successful_pid,
            "email": getattr(creds, "email", ""),
        }
        with self._lock:
            self._save_cache_to_disk(cache_data)
        return raw_models

    def fetch_quota_summary(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch quota summary from retrieveUserQuotaSummary."""
        try:
            creds = self.auth_manager.resolve_valid_credentials()
        except Exception as e:
            logger.debug("Could not resolve credentials for quota discovery: %s", e)
            return {}

        raw_pid = getattr(creds, "project_id", None)
        candidate_projects: List[str] = []
        if isinstance(raw_pid, str) and raw_pid.strip():
            candidate_projects.append(raw_pid.strip())
        if DEFAULT_PROJECT_ID not in candidate_projects:
            candidate_projects.append(DEFAULT_PROJECT_ID)

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
                        "Authorization": f"Bearer {getattr(creds, 'access_token', '')}",
                        "User-Agent": "Antigravity/2.11.0 (Windows NT 10.0; Win64; x64) Code-Assist/2026.03.0",
                        "X-Goog-Api-Client": "gl-go/1.24.0 gccl/2.11.0 antigravity/2.11.0",
                        "Client-Metadata": json.dumps({
                            "ideType": "ANTIGRAVITY",
                            "platform": "PLATFORM_WINDOWS",
                            "pluginType": "GEMINI",
                            "applicationVersion": "2.11.0",
                        }, separators=(",", ":")),
                    }

            for ep in [QUOTA_ENDPOINT, FALLBACK_QUOTA_ENDPOINT]:
                try:
                    req = urllib.request.Request(ep, data=payload_bytes, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
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
        raw_models = self.fetch_models(force_refresh=force_refresh)
        models_list: List[DiscoveredModel] = []

        for model_id, m in raw_models.items():
            if not isinstance(m, dict):
                continue
            disp = m.get("displayName") or model_id
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
            return ("gemini-3-flash-agent", {})

        norm = requested_model.lower().strip()
        if "/" in norm:
            norm = norm.split("/", 1)[1]

        models = self.get_discovered_models(force_refresh=False)
        model_map = {m.id.lower(): m for m in models}

        # 1. Exact match on model ID
        if norm in model_map:
            target = model_map[norm]
            return (target.id, target.to_openai_dict())

        # 2. Match by display name substring or slug alias
        alias_rules = [
            ("gemini-3.7-flash", ["gemini-3.7-flash-tiered", "gemini-3.7-flash-high", "gemini-3-flash-agent"]),
            ("gemini-3.7", ["gemini-3.7-flash-tiered", "gemini-3-flash-agent"]),
            ("gemini-3.6-flash", ["gemini-3.6-flash-high", "gemini-3.6-flash-medium", "gemini-3.6-flash-tiered"]),
            ("gemini-3.5-flash", ["gemini-3.5-flash-low", "gemini-3.5-flash-extra-low"]),
            ("gemini-3.1-pro", ["gemini-3.1-pro-high", "gemini-3.1-pro-low", "gemini-pro-agent"]),
            ("gemini-pro", ["gemini-3.1-pro-high", "gemini-3.1-pro-low"]),
            ("gemini-flash", ["gemini-3.7-flash-tiered", "gemini-3.6-flash-high", "gemini-3-flash"]),
            ("claude-sonnet-4-6", ["claude-sonnet-4-6"]),
            ("claude-sonnet-4.6", ["claude-sonnet-4-6"]),
            ("claude-3-7-sonnet", ["claude-sonnet-4-6"]),
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

        # 3. Fuzzy search in model IDs
        for mid, m in model_map.items():
            if norm in mid:
                return (m.id, m.to_openai_dict())

        # Fallback to recommended or first available
        for m in models:
            if "flash" in m.id:
                return (m.id, m.to_openai_dict())

        if models:
            return (models[0].id, models[0].to_openai_dict())

        return ("gemini-3-flash-agent", {})
