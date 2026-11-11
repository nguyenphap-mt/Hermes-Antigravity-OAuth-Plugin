"""Dedicated Gemini Web App Pool Manager & Sliding-Window Quota Tracker.

Manages `~/.hermes/gemini_web_pool.json` completely independently of the Code Assist OAuth pool:
- Supports Standalone Web Nodes (cookie-only) and Linked Nodes (same email as Code Assist).
- Tracks sliding-window 1h and 24h usage per model family (`argon`, `pro`, `flash`).
- Enforces Proactive High-Water Mark (`<= 10%` remaining) and per-model cooldowns.
- Supports 3 global routing modes: `hybrid_failover`, `web_first`, and `isolated`.
- Supports 3 rotation strategies: `sticky_session` (preserves server-side `[cid, rid, rcid]`),
  `least_used`, and `round_robin`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    _default_node_models_list,
    resolve_gemini_web_model,
    resolve_web_model_family,
)
from .session_manager import (
    GeminiWebSessionManager,
    get_hermes_dir,
    is_synthetic_oauth_cookie,
    parse_flexible_cookie_input,
)

logger = logging.getLogger(__name__)

VALID_ROUTING_MODES = {"hybrid_failover", "web_first", "isolated"}
VALID_WEB_STRATEGIES = {"sticky_session", "least_used", "round_robin"}

TIER_DEFAULT_LIMITS: Dict[str, Dict[str, int]] = {
    "ultra": {
        "argon_hourly_limit": 80,
        "argon_daily_limit": 500,
        "pro_hourly_limit": 100,
        "pro_daily_limit": 600,
        "flash_hourly_limit": 300,
        "flash_daily_limit": 2500,
    },
    "pro": {
        "argon_hourly_limit": 40,
        "argon_daily_limit": 200,
        "pro_hourly_limit": 50,
        "pro_daily_limit": 300,
        "flash_hourly_limit": 200,
        "flash_daily_limit": 1500,
    },
    "free": {
        "argon_hourly_limit": 10,
        "argon_daily_limit": 30,
        "pro_hourly_limit": 15,
        "pro_daily_limit": 50,
        "flash_hourly_limit": 100,
        "flash_daily_limit": 500,
    },
}


def _slugify_node_id(email_or_label: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (email_or_label or "").strip().lower()).strip("_")
    if not cleaned:
        cleaned = f"node_{int(time.time())}"
    return f"gweb_{cleaned[:48]}"


@dataclass
class GeminiWebNode:
    node_id: str
    email: str = ""
    display_name: str = ""
    linked_oauth_account_id: str = ""
    enabled: bool = True
    status: str = "ready"  # "ready", "expired", "cooldown", "unverified"
    detected_tier: str = "pro"  # "ultra", "pro", "free"
    available_models: List[Dict[str, str]] = field(default_factory=_default_node_models_list)
    default_web_model: str = "gemini-web-argon"
    quota_limits: Dict[str, int] = field(default_factory=lambda: dict(TIER_DEFAULT_LIMITS["pro"]))
    # Timestamps of requests in the last 24h grouped by family: {"argon": [...], "pro": [...], "flash": [...]}
    usage_timestamps: Dict[str, List[float]] = field(
        default_factory=lambda: {"argon": [], "pro": [], "flash": []}
    )
    total_requests: int = 0
    total_errors: int = 0
    last_used_at: float = 0.0
    last_error: str = ""
    model_cooldowns: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "email": self.email,
            "display_name": self.display_name,
            "linked_oauth_account_id": self.linked_oauth_account_id,
            "enabled": self.enabled,
            "status": self.status,
            "detected_tier": self.detected_tier,
            "available_models": self.available_models,
            "default_web_model": self.default_web_model,
            "quota_limits": self.quota_limits,
            "usage_timestamps": self.usage_timestamps,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "last_used_at": self.last_used_at,
            "last_error": self.last_error,
            "model_cooldowns": self.model_cooldowns,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GeminiWebNode":
        tier = str(d.get("detected_tier") or "pro").lower()
        default_limits = dict(TIER_DEFAULT_LIMITS.get(tier, TIER_DEFAULT_LIMITS["pro"]))
        if isinstance(d.get("quota_limits"), dict):
            for k, v in d["quota_limits"].items():
                try:
                    default_limits[k] = max(1, int(v))
                except Exception:
                    pass
        raw_ts = d.get("usage_timestamps")
        ts_map: Dict[str, List[float]] = {"argon": [], "pro": [], "flash": []}
        if isinstance(raw_ts, dict):
            for fam in ("argon", "pro", "flash"):
                if isinstance(raw_ts.get(fam), list):
                    ts_map[fam] = [float(x) for x in raw_ts[fam] if isinstance(x, (int, float))]

        raw_avail = d.get("available_models")
        merged_avail: List[Dict[str, str]] = []
        seen_ids: Set[str] = set()
        for m in _default_node_models_list():
            mid = str(m.get("id") or "").strip()
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                merged_avail.append(m)
        if isinstance(raw_avail, list):
            for m in raw_avail:
                if isinstance(m, dict) and m.get("id"):
                    mid = str(m["id"]).strip()
                    if mid and mid not in seen_ids:
                        seen_ids.add(mid)
                        merged_avail.append(m)

        return cls(
            node_id=str(d.get("node_id") or _slugify_node_id(str(d.get("email") or ""))),
            email=str(d.get("email") or ""),
            display_name=str(d.get("display_name") or d.get("email") or "Gemini Web Node"),
            linked_oauth_account_id=str(d.get("linked_oauth_account_id") or ""),
            enabled=bool(d.get("enabled", True)),
            status=str(d.get("status") or "ready"),
            detected_tier=tier,
            available_models=merged_avail,
            default_web_model=str(d.get("default_web_model") or "gemini-web-4-argon"),
            quota_limits=default_limits,
            usage_timestamps=ts_map,
            total_requests=int(d.get("total_requests") or 0),
            total_errors=int(d.get("total_errors") or 0),
            last_used_at=float(d.get("last_used_at") or 0.0),
            last_error=str(d.get("last_error") or ""),
            model_cooldowns={
                str(k): float(v)
                for k, v in (d.get("model_cooldowns") or {}).items()
                if isinstance(v, (int, float))
            },
        )


class GeminiWebPoolManager:
    """Dedicated manager for the Gemini Web App quota pool and server-side conversation contexts."""

    _lock = threading.RLock()
    _rr_index: int = 0
    # In-memory cache mapping Hermes session_key -> {"node_id": str, "cid": str, "rid": str, "rcid": str, "turn_count": int, "updated_at": float}
    _conversation_contexts: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        hermes_dir: Optional[Path] = None,
        session_manager: Optional[GeminiWebSessionManager] = None,
    ) -> None:
        self.hermes_dir = hermes_dir or get_hermes_dir()
        self.pool_file = self.hermes_dir / "gemini_web_pool.json"
        self.session_manager = session_manager or GeminiWebSessionManager(self.hermes_dir)

    def _default_config(self) -> Dict[str, Any]:
        return {
            "routing_mode": "hybrid_failover",
            "rotation_strategy": "sticky_session",
            "auto_rotate_cookies": True,
            "rotate_interval_sec": 540,
            "proactive_switch_remaining_pct": 10.0,
            "preserve_server_context": True,
        }

    def _load_pool_raw(self) -> Tuple[Dict[str, Any], List[GeminiWebNode]]:
        if not self.pool_file.is_file():
            return self._default_config(), []
        try:
            with open(self.pool_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._default_config(), []
            cfg = self._default_config()
            if isinstance(data.get("config"), dict):
                cfg.update(data["config"])
            nodes_raw = data.get("nodes") or []
            nodes = [GeminiWebNode.from_dict(item) for item in nodes_raw if isinstance(item, dict)]
            tier_rank = {"free": 0, "pro": 1, "ultra": 2}
            dirty = False
            for n in nodes:
                raw_sess = self.session_manager.get_session(n.node_id)
                if raw_sess:
                    raw_cks = raw_sess.get("cookies") or {}
                    if is_synthetic_oauth_cookie(str(raw_cks.get("__Secure-1PSID") or "")) or is_synthetic_oauth_cookie(
                        str(raw_sess.get("snlm0e") or "")
                    ):
                        self.session_manager.delete_session(n.node_id)
                ck_health = self.session_manager.get_public_cookie_health(n.node_id)
                if not ck_health.get("is_authentic_web_session"):
                    if n.status == "ready":
                        n.status = "unverified"
                        n.last_error = "Chưa gắn phiên Cookie gemini.google.com thật (Chờ đăng nhập Web)."
                        dirty = True

                linked = self.session_manager._resolve_linked_google_account(
                    n.node_id, email_hint=n.email or n.linked_oauth_account_id
                )
                if linked:
                    l_tier = str(linked.get("tier") or "free").lower()
                    if tier_rank.get(l_tier, 0) > tier_rank.get(n.detected_tier, 0):
                        old_tier = n.detected_tier
                        n.detected_tier = l_tier
                        # Upgrade quota_limits if still on old default limits
                        old_defaults = TIER_DEFAULT_LIMITS.get(old_tier, TIER_DEFAULT_LIMITS["free"])
                        if n.quota_limits.get("argon_hourly_limit") == old_defaults.get("argon_hourly_limit"):
                            n.quota_limits = dict(TIER_DEFAULT_LIMITS.get(l_tier, TIER_DEFAULT_LIMITS["pro"]))
                        dirty = True
                    tier_label = (
                        "Google AI Ultra"
                        if n.detected_tier == "ultra"
                        else ("Google AI Pro" if n.detected_tier == "pro" else "Free")
                    )
                    if n.detected_tier in ("pro", "ultra") and n.display_name and "(Free)" in n.display_name:
                        n.display_name = n.display_name.replace("(Free)", f"({tier_label})")
                        dirty = True
                    elif n.detected_tier == "ultra" and n.display_name and "(Google AI Pro)" in n.display_name:
                        n.display_name = n.display_name.replace("(Google AI Pro)", f"({tier_label})")
                        dirty = True
            if dirty:
                try:
                    self._save_pool_raw(cfg, nodes)
                except Exception:
                    pass
            return cfg, nodes
        except Exception as e:
            logger.warning("Failed to read gemini_web_pool.json: %s", e)
            return self._default_config(), []

    def _save_pool_raw(self, config: Dict[str, Any], nodes: List[GeminiWebNode]) -> None:
        self.hermes_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": time.time(),
            "config": config,
            "nodes": [n.to_dict() for n in nodes],
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.hermes_dir),
            prefix=".gweb_pool_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(self.pool_file))
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            raise

    # ─── Configuration Management ─────────────────────────────────────────

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            cfg, _ = self._load_pool_raw()
            return cfg

    def update_config(
        self,
        routing_mode: Optional[str] = None,
        rotation_strategy: Optional[str] = None,
        auto_rotate_cookies: Optional[bool] = None,
        preserve_server_context: Optional[bool] = None,
        proactive_switch_remaining_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            if routing_mode and routing_mode in VALID_ROUTING_MODES:
                cfg["routing_mode"] = routing_mode
            if rotation_strategy and rotation_strategy in VALID_WEB_STRATEGIES:
                cfg["rotation_strategy"] = rotation_strategy
            if auto_rotate_cookies is not None:
                cfg["auto_rotate_cookies"] = bool(auto_rotate_cookies)
            if preserve_server_context is not None:
                cfg["preserve_server_context"] = bool(preserve_server_context)
            if proactive_switch_remaining_pct is not None:
                cfg["proactive_switch_remaining_pct"] = max(0.0, min(50.0, float(proactive_switch_remaining_pct)))
            self._save_pool_raw(cfg, nodes)
            return cfg

    # ─── Sliding-Window Quota Calculation ─────────────────────────────────

    def _prune_old_timestamps(self, node: GeminiWebNode, now: Optional[float] = None) -> None:
        now_ts = now if now is not None else time.time()
        cutoff_24h = now_ts - 86400.0
        for fam in ("argon", "pro", "flash"):
            ts_list = node.usage_timestamps.get(fam) or []
            node.usage_timestamps[fam] = [t for t in ts_list if t > cutoff_24h]
        # Prune expired model cooldowns
        expired_keys = [k for k, until in node.model_cooldowns.items() if until <= now_ts]
        for k in expired_keys:
            del node.model_cooldowns[k]

    def compute_node_quota_summary(self, node: GeminiWebNode, now: Optional[float] = None) -> Dict[str, Any]:
        """Compute real-time 1h & 24h sliding-window usage and remaining percentage per model family."""
        now_ts = now if now is not None else time.time()
        self._prune_old_timestamps(node, now_ts)
        cutoff_1h = now_ts - 3600.0

        summary: Dict[str, Any] = {}
        for fam in ("argon", "pro", "flash"):
            ts_24h = node.usage_timestamps.get(fam) or []
            count_24h = len(ts_24h)
            count_1h = sum(1 for t in ts_24h if t > cutoff_1h)

            limit_1h = max(1, int(node.quota_limits.get(f"{fam}_hourly_limit") or 40))
            limit_24h = max(1, int(node.quota_limits.get(f"{fam}_daily_limit") or 200))

            rem_1h_pct = max(0.0, 100.0 - (count_1h / limit_1h) * 100.0)
            rem_24h_pct = max(0.0, 100.0 - (count_24h / limit_24h) * 100.0)
            effective_pct = round(min(rem_1h_pct, rem_24h_pct), 1)

            cooldown_until = float(node.model_cooldowns.get(fam) or 0.0)
            cooldown_rem = max(0, int(cooldown_until - now_ts)) if cooldown_until > now_ts else 0
            reset_label = ""
            if cooldown_rem > 0 and cooldown_until > now_ts:
                tz_vn = datetime.timezone(datetime.timedelta(hours=7))
                reset_label = datetime.datetime.fromtimestamp(cooldown_until, tz=tz_vn).strftime("%H:%M")

            summary[f"{fam}_1h_count"] = count_1h
            summary[f"{fam}_1h_limit"] = limit_1h
            summary[f"{fam}_24h_count"] = count_24h
            summary[f"{fam}_24h_limit"] = limit_24h
            summary[f"{fam}_remaining_pct"] = 0.0 if cooldown_rem > 0 else effective_pct
            summary[f"{fam}_cooldown_seconds"] = cooldown_rem
            summary[f"{fam}_cooldown_until"] = cooldown_until if cooldown_rem > 0 else 0.0
            summary[f"{fam}_reset_at_label"] = reset_label

        return summary

    # ─── Node CRUD & Lifecycle ────────────────────────────────────────────

    def list_nodes(self) -> List[GeminiWebNode]:
        with self._lock:
            _, nodes = self._load_pool_raw()
            now_ts = time.time()
            for n in nodes:
                self._prune_old_timestamps(n, now_ts)
            return nodes

    def get_node(self, node_id: str) -> Optional[GeminiWebNode]:
        with self._lock:
            _, nodes = self._load_pool_raw()
            for n in nodes:
                if n.node_id == node_id or (n.email and n.email.lower() == node_id.lower()):
                    self._prune_old_timestamps(n)
                    return n
            return None

    async def import_or_update_node(
        self,
        raw_cookie_input: str = "",
        psid: str = "",
        psidts: str = "",
        email: str = "",
        display_name: str = "",
        node_id: str = "",
        linked_oauth_account_id: str = "",
        verify_immediately: bool = True,
        http_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Parse cookies, save to `gemini_web_sessions.json`, optionally run live handshake, and register node."""
        cookies = parse_flexible_cookie_input(raw_cookie_input, psid=psid, psidts=psidts)
        if not cookies.get("__Secure-1PSID"):
            return {
                "ok": False,
                "error": "Không tìm thấy cookie __Secure-1PSID trong dữ liệu đầu vào. Hãy dán chuỗi Cookie, JSON Cookie-Editor, hoặc cURL hợp lệ.",
            }

        resolved_id = (node_id or "").strip() or _slugify_node_id(email or cookies["__Secure-1PSID"][:16])
        self.session_manager.save_session(node_id=resolved_id, cookies=cookies)

        probe_res: Dict[str, Any] = {
            "ok": True,
            "status": "ready",
            "email": email,
            "detected_tier": "pro",
            "available_models": _default_node_models_list(),
        }
        if verify_immediately:
            probe_res = await self.session_manager.handshake_and_probe_models(
                resolved_id, http_client=http_client
            )

        detected_email = (email or probe_res.get("email") or "").strip().lower()
        if not node_id and detected_email:
            # Re-key node_id cleanly by email if discovered during handshake
            email_based_id = _slugify_node_id(detected_email)
            if email_based_id != resolved_id:
                old_sess = self.session_manager.get_session(resolved_id) or {}
                self.session_manager.save_session(
                    node_id=email_based_id,
                    cookies=old_sess.get("cookies") or cookies,
                    snlm0e=old_sess.get("snlm0e") or "",
                    cfb2h=old_sess.get("cfb2h") or "",
                    fsid=old_sess.get("fsid") or "",
                )
                self.session_manager.delete_session(resolved_id)
                resolved_id = email_based_id

        tier = str(probe_res.get("detected_tier") or "pro").lower()
        status = "ready" if probe_res.get("ok") else str(probe_res.get("status") or "unverified")

        with self._lock:
            cfg, nodes = self._load_pool_raw()
            existing_node: Optional[GeminiWebNode] = None
            for n in nodes:
                if n.node_id == resolved_id or (detected_email and n.email.lower() == detected_email):
                    existing_node = n
                    break

            if existing_node:
                existing_node.email = detected_email or existing_node.email
                existing_node.display_name = (
                    display_name
                    or existing_node.display_name
                    or detected_email
                    or resolved_id
                )
                if linked_oauth_account_id:
                    existing_node.linked_oauth_account_id = linked_oauth_account_id
                old_tier = existing_node.detected_tier
                existing_node.status = status
                existing_node.detected_tier = tier
                if old_tier != tier:
                    old_defaults = TIER_DEFAULT_LIMITS.get(old_tier, TIER_DEFAULT_LIMITS["free"])
                    if existing_node.quota_limits.get("argon_hourly_limit") == old_defaults.get("argon_hourly_limit"):
                        existing_node.quota_limits = dict(TIER_DEFAULT_LIMITS.get(tier, TIER_DEFAULT_LIMITS["pro"]))
                if probe_res.get("available_models"):
                    existing_node.available_models = probe_res["available_models"]
                existing_node.last_error = "" if probe_res.get("ok") else str(probe_res.get("error") or "")
                target_node = existing_node
            else:
                target_node = GeminiWebNode(
                    node_id=resolved_id,
                    email=detected_email,
                    display_name=display_name or detected_email or resolved_id,
                    linked_oauth_account_id=linked_oauth_account_id,
                    enabled=True,
                    status=status,
                    detected_tier=tier,
                    available_models=probe_res.get("available_models") or _default_node_models_list(),
                    default_web_model="gemini-web-argon",
                    quota_limits=dict(TIER_DEFAULT_LIMITS.get(tier, TIER_DEFAULT_LIMITS["pro"])),
                )
                nodes.append(target_node)

            self._save_pool_raw(cfg, nodes)

        return {
            "ok": bool(probe_res.get("ok", True)),
            "node": self.format_node_for_dashboard(target_node),
            "handshake": probe_res,
        }

    def toggle_node(self, node_id: str, enabled: Optional[bool] = None) -> Optional[GeminiWebNode]:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            for n in nodes:
                if n.node_id == node_id or (n.email and n.email.lower() == node_id.lower()):
                    n.enabled = (not n.enabled) if enabled is None else bool(enabled)
                    self._save_pool_raw(cfg, nodes)
                    return n
            return None

    def update_node_limits(
        self,
        node_id: str,
        limits: Optional[Dict[str, int]] = None,
        default_web_model: Optional[str] = None,
        reset_usage: bool = False,
    ) -> Optional[GeminiWebNode]:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            for n in nodes:
                if n.node_id == node_id or (n.email and n.email.lower() == node_id.lower()):
                    if limits:
                        for k, v in limits.items():
                            if k in n.quota_limits and v is not None:
                                n.quota_limits[k] = max(1, int(v))
                    if default_web_model:
                        n.default_web_model = resolve_gemini_web_model(default_web_model)
                    if reset_usage:
                        n.usage_timestamps = {"argon": [], "pro": [], "flash": []}
                        n.model_cooldowns = {}
                        if n.status == "cooldown":
                            n.status = "ready"
                    self._save_pool_raw(cfg, nodes)
                    return n
            return None

    def remove_node(self, node_id: str) -> bool:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            kept = [
                n for n in nodes
                if n.node_id != node_id and (not n.email or n.email.lower() != node_id.lower())
            ]
            if len(kept) == len(nodes):
                return False
            removed_ids = {n.node_id for n in nodes} - {n.node_id for n in kept}
            self._save_pool_raw(cfg, kept)
            for rid in removed_ids:
                self.session_manager.delete_session(rid)
            return True

    # ─── Routing & Quota-Aware Node Selection ─────────────────────────────

    def has_available_node(self, model_name: str = "gemini-web-argon") -> bool:
        return self.select_node_for_model(model_name) is not None

    def select_node_for_model(
        self,
        model_name: str = "gemini-web-argon",
        session_key: str = "",
        exclude_node_ids: Optional[Set[str]] = None,
    ) -> Optional[GeminiWebNode]:
        """Select the healthiest ready Gemini Web node for the requested model."""
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            if not nodes:
                return None

            family = resolve_web_model_family(model_name)
            excluded = exclude_node_ids or set()
            now_ts = time.time()
            high_water_mark = float(cfg.get("proactive_switch_remaining_pct") or 10.0)
            strategy = str(cfg.get("rotation_strategy") or "sticky_session")

            ready_above_hwm: List[Tuple[float, GeminiWebNode]] = []
            ready_below_hwm: List[Tuple[float, GeminiWebNode]] = []

            for n in nodes:
                if not n.enabled or n.node_id in excluded:
                    continue
                if n.status not in ("ready", "cooldown"):
                    continue
                # Verify authentic Gemini Web cookie exists
                ck_health = self.session_manager.get_public_cookie_health(n.node_id)
                if not ck_health.get("has_1psid") or not ck_health.get("is_authentic_web_session"):
                    continue

                q_sum = self.compute_node_quota_summary(n, now_ts)
                if q_sum.get(f"{family}_cooldown_seconds", 0) > 0:
                    continue

                rem_pct = float(q_sum.get(f"{family}_remaining_pct", 100.0))
                tier_bonus = 30.0 if n.detected_tier == "ultra" else (20.0 if n.detected_tier == "pro" else 5.0)
                score = tier_bonus + rem_pct * 0.7

                if rem_pct > high_water_mark:
                    ready_above_hwm.append((score, n))
                elif rem_pct > 0.0:
                    ready_below_hwm.append((score, n))

            pool_to_use = ready_above_hwm if ready_above_hwm else ready_below_hwm
            if not pool_to_use:
                return None

            # 1. Sticky Session: reuse the node that already holds [cid, rid, rcid] for this conversation
            if strategy == "sticky_session" and session_key:
                ctx = self._conversation_contexts.get(session_key)
                if ctx:
                    sticky_id = ctx.get("node_id")
                    for _, candidate_node in pool_to_use:
                        if candidate_node.node_id == sticky_id:
                            return candidate_node

            # 2. Strategy-based selection
            if strategy == "round_robin":
                idx = self._rr_index % len(pool_to_use)
                self._rr_index += 1
                return pool_to_use[idx][1]

            # Default / least_used: sort by highest score, then lowest recent usage
            pool_to_use.sort(key=lambda item: (-item[0], item[1].last_used_at))
            return pool_to_use[0][1]

    def record_web_usage(
        self,
        node_id: str,
        model_name: str,
        success: bool = True,
        error_msg: str = "",
    ) -> None:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            now_ts = time.time()
            family = resolve_web_model_family(model_name)
            for n in nodes:
                if n.node_id == node_id:
                    self._prune_old_timestamps(n, now_ts)
                    if success:
                        n.usage_timestamps.setdefault(family, []).append(now_ts)
                        n.total_requests += 1
                        n.last_used_at = now_ts
                        n.last_error = ""
                        if n.status == "unverified":
                            n.status = "ready"
                    else:
                        n.total_errors += 1
                        n.last_error = error_msg[:300]
                    self._save_pool_raw(cfg, nodes)
                    break

    def mark_web_model_cooldown(
        self,
        node_id: str,
        model_name: str,
        cooldown_seconds: float = 1800.0,
        reason: str = "",
    ) -> None:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            now_ts = time.time()
            family = resolve_web_model_family(model_name)
            for n in nodes:
                if n.node_id == node_id:
                    n.model_cooldowns[family] = now_ts + max(60.0, cooldown_seconds)
                    if reason:
                        n.last_error = reason[:300]
                    self._save_pool_raw(cfg, nodes)
                    break

    # ─── Server-Side Conversation Context (`[cid, rid, rcid]`) ────────────

    @staticmethod
    def compute_session_key(openai_payload: Dict[str, Any]) -> str:
        """Derive a stable conversation session key from OpenAI payload or first user/system messages."""
        explicit_id = (
            openai_payload.get("session_id")
            or openai_payload.get("conversation_id")
        )
        if explicit_id:
            return f"sess_{explicit_id}"
        messages = openai_payload.get("messages") or []
        user_id = str(openai_payload.get("user") or "").strip()
        if not messages:
            return f"sess_{user_id}" if user_id else ""
        # Hash the first system + first user message so multi-turn tool calls in the same task share a key,
        # while a brand-new conversation started by the same static `user` gets a fresh key.
        seed_parts: List[str] = []
        found_sys = False
        found_usr = False
        for m in messages:
            if not isinstance(m, dict):
                continue
            r = str(m.get("role") or "").lower()
            if r in ("system", "developer") and not found_sys:
                seed_parts.append(f"sys:{str(m.get('content'))[:400]}")
                found_sys = True
            elif r == "user" and not found_usr:
                seed_parts.append(f"usr:{str(m.get('content'))[:400]}")
                found_usr = True
            if found_sys and found_usr:
                break
        if not seed_parts:
            for m in messages[:2]:
                if isinstance(m, dict):
                    seed_parts.append(f"{m.get('role')}:{str(m.get('content'))[:400]}")
        digest = hashlib.sha256("|".join(seed_parts).encode("utf-8", errors="ignore")).hexdigest()[:20]
        if user_id:
            return f"sess_{user_id}_{digest}"
        return f"conv_{digest}"

    @staticmethod
    def compute_history_hash(
        messages: List[Dict[str, Any]],
        include_trailing: bool = False,
    ) -> str:
        """Compute a deterministic SHA-256 fingerprint of conversation history up to the last assistant turn."""
        if not messages:
            return ""
        if include_trailing:
            target_slice = messages
        else:
            last_assistant_idx = -1
            for idx in range(len(messages) - 1, -1, -1):
                m = messages[idx]
                if isinstance(m, dict) and str(m.get("role") or "").lower() == "assistant":
                    last_assistant_idx = idx
                    break
            if last_assistant_idx < 0:
                return ""
            target_slice = messages[: last_assistant_idx + 1]

        norm: List[str] = []
        for m in target_slice:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "user").lower()
            raw_c = m.get("content")
            if raw_c is None:
                c_str = ""
            elif isinstance(raw_c, str):
                c_str = raw_c.strip()
            elif isinstance(raw_c, list):
                c_parts: List[str] = []
                for item in raw_c:
                    if isinstance(item, str):
                        c_parts.append(item)
                    elif isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                        c_parts.append(str(item["text"]))
                c_str = "\n".join(c_parts).strip()
            else:
                c_str = str(raw_c).strip()

            tc_names: List[str] = []
            for tc in m.get("tool_calls") or []:
                if isinstance(tc, dict):
                    fn = tc.get("function") or {}
                    tc_names.append(str(fn.get("name") or ""))
            norm.append(f"{role}|{c_str}|{'^'.join(tc_names)}")
        return hashlib.sha256("\n".join(norm).encode("utf-8", errors="ignore")).hexdigest()[:24]

    def get_conversation_context(
        self,
        session_key: str,
        node_id: str,
        expected_history_hash: Optional[str] = None,
    ) -> Optional[List[str]]:
        if not session_key:
            return None
        with self._lock:
            cfg, _ = self._load_pool_raw()
            if not cfg.get("preserve_server_context", True):
                return None
            ctx = self._conversation_contexts.get(session_key)
            if not ctx or ctx.get("node_id") != node_id:
                return None
            if time.time() - float(ctx.get("updated_at") or 0.0) > 3600.0:
                del self._conversation_contexts[session_key]
                return None
            if expected_history_hash is not None:
                if not expected_history_hash:
                    # Turn 1 (no assistant turn in messages yet): never reuse stale context
                    del self._conversation_contexts[session_key]
                    return None
                stored_hash = str(ctx.get("history_hash") or "")
                if stored_hash and stored_hash != expected_history_hash:
                    # Turn desync detected (e.g. intermediate turn ran on another node or Code Assist)
                    del self._conversation_contexts[session_key]
                    return None
            return [
                str(ctx.get("cid") or ""),
                str(ctx.get("rid") or ""),
                str(ctx.get("rcid") or ""),
            ]

    def save_conversation_context(
        self,
        session_key: str,
        node_id: str,
        cid: str,
        rid: str,
        rcid: str,
        history_hash: str = "",
    ) -> None:
        if not session_key or not cid:
            return
        with self._lock:
            self._conversation_contexts[session_key] = {
                "node_id": node_id,
                "cid": cid,
                "rid": rid,
                "rcid": rcid,
                "history_hash": history_hash,
                "updated_at": time.time(),
            }

    def invalidate_conversation_context(self, session_key: str, node_id: str = "") -> None:
        if not session_key:
            return
        with self._lock:
            ctx = self._conversation_contexts.get(session_key)
            if ctx and (not node_id or ctx.get("node_id") == node_id):
                del self._conversation_contexts[session_key]

    # ─── Dashboard Serialization ──────────────────────────────────────────

    def format_node_for_dashboard(self, node: GeminiWebNode) -> Dict[str, Any]:
        q_sum = self.compute_node_quota_summary(node)
        ck_health = self.session_manager.get_public_cookie_health(node.node_id)
        return {
            "node_id": node.node_id,
            "email": node.email,
            "display_name": node.display_name or node.email or node.node_id,
            "linked_oauth_account_id": node.linked_oauth_account_id,
            "enabled": node.enabled,
            "status": node.status,
            "detected_tier": node.detected_tier,
            "tier_badge": (
                "GOOGLE AI ULTRA"
                if node.detected_tier == "ultra"
                else ("GOOGLE AI PRO" if node.detected_tier == "pro" else "FREE TIER")
            ),
            "available_models": node.available_models,
            "default_web_model": node.default_web_model,
            "cookie_health": ck_health,
            "quota_limits": node.quota_limits,
            "quota_summary": q_sum,
            "total_requests": node.total_requests,
            "total_errors": node.total_errors,
            "last_used_at": node.last_used_at,
            "last_error": node.last_error,
        }

    def get_dashboard_pool_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            cfg, nodes = self._load_pool_raw()
            formatted = [self.format_node_for_dashboard(n) for n in nodes]
            ready_count = sum(
                1 for item in formatted
                if item["enabled"]
                and item["status"] == "ready"
                and item["cookie_health"].get("has_1psid")
                and item["cookie_health"].get("is_authentic_web_session")
            )
            return {
                "ok": True,
                "config": cfg,
                "total_nodes": len(formatted),
                "ready_nodes": ready_count,
                "nodes": formatted,
            }
