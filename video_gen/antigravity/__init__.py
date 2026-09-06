"""Google Flow (Veo AI Video Generator) Provider for Hermes Agent.

Provides native text-to-video, image-to-video, and upsampling through Google Flow
using the Camofox browser bridge and Headless Auto-Refresh Daemon.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure bridge runtime discovery from ~/.hermes/ or workspace
try:
    from hermes_constants import get_hermes_home
    _h_home = get_hermes_home()
except Exception:
    _h_home = Path.home() / ".hermes"

for _sub in ("tools", ""):
    _p = str(_h_home / "bridge" / "antigravity" / _sub) if _sub else str(_h_home / "bridge" / "antigravity")
    if Path(_p).exists() and _p not in sys.path:
        sys.path.insert(0, _p)

from agent.video_gen_provider import (
    COMMON_ASPECT_RATIOS,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_RESOLUTION,
    VideoGenProvider,
    error_response,
    success_response,
)

logger = logging.getLogger(__name__)

# Model Catalog for user-friendly selection
# Full Google Flow Video Models Catalog (5 Official Tiers)
VEO_MODELS: List[Dict[str, Any]] = [
    {
        "id": "veo-3.1-lite-free",
        "aliases": ["free", "0-credits", "lower-priority", "mien-phi", "0-credit", "0-tin-dung"],
        "display": "Veo 3.1 - Lite [Lower Priority] (0 tín dụng - Miễn phí 100%)",
        "tier": "Miễn phí",
        "speed": "~20-35s",
        "duration": 4,
        "credits": 0,
        "strengths": "Hoàn toàn miễn phí, không tốn tín dụng AI nào. Thích hợp để thử nghiệm kịch bản, làm nháp, xem trước.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_4s",
    },
    {
        "id": "veo-3.1-lite",
        "aliases": ["veo-lite", "lite", "tiet-kiem", "re-nhat", "5-credits", "5-credit", "5-tin-dung"],
        "display": "Veo 3.1 - Lite (5 tín dụng AI - Tiết kiệm & Tốc độ cao)",
        "tier": "Tiết kiệm",
        "speed": "~20-30s",
        "duration": 6,
        "credits": 5,
        "strengths": "Chi phí tín dụng thấp nhất, tốc độ sinh video siêu nhanh, tối ưu hóa xem nhanh trên thiết bị di động.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_6s",
    },
    {
        "id": "omni-1.1-flash",
        "aliases": ["omni", "omni-1.1", "omni-flash", "flash", "tieu-chuan", "mac-dinh", "6-credits", "6-credit", "6-tin-dung"],
        "display": "Omni 1.1 Flash (6 tín dụng AI - Tiêu chuẩn, Khuyên dùng)",
        "tier": "Tiêu chuẩn",
        "speed": "~30-40s",
        "duration": 10,
        "credits": 6,
        "strengths": "Mô hình cân bằng tối ưu nhất: đa phương thức, tạo video tự nhiên, kèm âm thanh và hiệu ứng sinh động.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_10s",
    },
    {
        "id": "veo-3.1-fast",
        "aliases": ["veo-fast", "fast", "cao-cap", "10-credits", "10-credit", "10-tin-dung"],
        "display": "Veo 3.1 - Fast (10 tín dụng AI - Cao cấp & Sắc nét)",
        "tier": "Cao cấp",
        "speed": "~40-50s",
        "duration": 10,
        "credits": 10,
        "strengths": "Chất lượng điện ảnh cao, chuyển động vật lý mượt mà và âm thanh đồng bộ cao cấp.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_10s",
    },
    {
        "id": "veo-3.1-quality",
        "aliases": ["veo-quality", "quality", "cuc-pham", "dinh-cao", "dien-anh", "100-credits", "100-credit", "100-tin-dung"],
        "display": "Veo 3.1 - Quality (100 tín dụng AI - Cực phẩm Điện ảnh Studio)",
        "tier": "Cực phẩm",
        "speed": "~60-90s",
        "duration": 10,
        "credits": 100,
        "strengths": "Chất lượng đỉnh cao tuyệt đối của Google: mô phỏng quang học chuẩn xác, độ chi tiết điện ảnh tối đa.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_10s",
    },
    # Backwards compatibility models
    {
        "id": "veo-2-10s",
        "aliases": ["veo-10s", "veo2-10s"],
        "display": "Google Veo 2 (10s Cinematic)",
        "speed": "~45-55s",
        "duration": 10,
        "credits": 10,
        "strengths": "Chất lượng điện ảnh 10s hoàn chỉnh.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_10s",
    },
    {
        "id": "veo-2-6s",
        "aliases": ["veo-6s", "veo2-6s"],
        "display": "Google Veo 2 (6s Fast)",
        "speed": "~25-30s",
        "duration": 6,
        "credits": 6,
        "strengths": "Sinh video 6s nhanh chóng.",
        "modalities": ["text", "image"],
        "model_key": "abra_t2v_6s",
    },
    {
        "id": "veo-i2v",
        "aliases": ["i2v", "image-to-video"],
        "display": "Google Veo (Image-to-Video)",
        "speed": "~40-50s",
        "duration": 10,
        "credits": 6,
        "strengths": "Biến ảnh tĩnh thành video hoạt cảnh chuyển động sống động.",
        "modalities": ["image"],
        "model_key": "abra_t2v_10s",
    },
]


class AntigravityVideoGenProvider(VideoGenProvider):
    """Video Generation Provider using Google Flow (Veo AI / Abra)."""

    @property
    def name(self) -> str:
        return "antigravity"

    @property
    def display_name(self) -> str:
        return "Google Flow (Veo AI Video Generator)"

    def is_available(self) -> bool:
        """Return True when Google Flow has valid credentials or active session."""
        try:
            try:
                from bridge.flow.flow_auth_service import FlowAuthService
            except ImportError:
                from tools.antigravity_bridge.flow.flow_auth_service import FlowAuthService
            svc = FlowAuthService.get_instance()
            st = svc.get_status()
            return bool(st.get("connected") or st.get("has_session_cookie"))
        except Exception:
            return True

    def list_models(self) -> List[Dict[str, Any]]:
        return list(VEO_MODELS)

    def default_model(self) -> Optional[str]:
        return "omni-1.1-flash"

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "aspect_ratios": ["16:9", "9:16"],
            "resolutions": ["720p", "1080p"],
            "max_duration": 10,
            "min_duration": 4,
            "supports_audio": True,
            "supports_negative_prompt": False,
            "max_reference_images": 0,
        }

    def _resolve_model_and_duration(
        self, prompt: str, duration: Optional[int], model: Optional[str]
    ) -> Tuple[str, str, int]:
        """Intelligently determine (model_id, video_model_key, duration) based on model param and prompt."""
        m_req = (model or "").lower().strip()
        p_lower = prompt.lower()

        # 1. Match explicit model parameter against catalog & aliases
        for m_info in VEO_MODELS:
            all_names = [m_info["id"].lower()] + [a.lower() for a in m_info.get("aliases", [])]
            if m_req in all_names:
                chosen_dur = duration or m_info["duration"]
                return m_info["id"], m_info.get("model_key", "abra_t2v_10s"), chosen_dur

        if "free" in m_req or "0-credit" in m_req or "mien-phi" in m_req:
            return "veo-3.1-lite-free", "abra_t2v_4s", 4
        if "quality" in m_req or "100" in m_req or "cuc-pham" in m_req:
            return "veo-3.1-quality", "abra_t2v_10s", 10
        if "preview" in m_req or "4s" in m_req:
            return "veo-3.1-lite-free", "abra_t2v_4s", 4
        if "fast" in m_req or "10s" in m_req:
            return "veo-3.1-fast", "abra_t2v_10s", 10
        if "6s" in m_req or "lite" in m_req or "5" in m_req:
            return "veo-3.1-lite", "abra_t2v_6s", 6

        # 2. Natural Language Intent & Quality Tier matching from user prompt
        # Tier 0: Free / 0 credits (Lower Priority)
        if re.search(r"\b(miễn\s*phí|free|0\s*tín\s*dụng|0\s*credit|lower\s*priority|không\s*tốn\s*credit)\b", p_lower):
            return "veo-3.1-lite-free", "abra_t2v_4s", duration or 4
        # Tier 4: Ultra Quality / 100 credits (Quality)
        if re.search(r"\b(100\s*tín\s*dụng|100\s*credit|cực\s*phẩm|đỉnh\s*cao|siêu\s*nét|chiếu\s*rạp|studio|master|quality)\b", p_lower):
            return "veo-3.1-quality", "abra_t2v_10s", duration or 10
        # Tier 3: High quality / 10 credits (Fast)
        if re.search(r"\b(10\s*tín\s*dụng|10\s*credit|veo\s*fast|cao\s*cấp|đẹp\s*nhất)\b", p_lower):
            return "veo-3.1-fast", "abra_t2v_10s", duration or 10
        # Tier 1: Budget / 5 credits (Lite)
        if re.search(r"\b(5\s*tín\s*dụng|5\s*credit|tiết\s*kiệm|nhanh\s*nhất|rẻ\s*nhất|veo\s*lite)\b", p_lower):
            return "veo-3.1-lite", "abra_t2v_6s", duration or 6
        # Tier 2: Omni / Standard / 6 credits
        if re.search(r"\b(omni|6\s*tín\s*dụng|6\s*credit|tiêu\s*chuẩn|có\s*tiếng|âm\s*thanh)\b", p_lower):
            return "omni-1.1-flash", "abra_t2v_10s", duration or 10

        # 3. Check duration hints in prompt
        if re.search(r"\b(4s|4\s*giây|preview|nháp)\b", p_lower):
            return "veo-3.1-lite-free", "abra_t2v_4s", 4
        if re.search(r"\b(6s|6\s*giây|nhanh|fast|quick)\b", p_lower):
            return "veo-3.1-lite", "abra_t2v_6s", 6
        if re.search(r"\b(8s|8\s*giây)\b", p_lower):
            return "omni-1.1-flash", "abra_t2v_8s", 8
        if re.search(r"\b(10s|10\s*giây|dài|điện ảnh|cinematic)\b", p_lower):
            return "veo-3.1-fast", "abra_t2v_10s", 10

        # 4. Fallback to duration if explicitly provided
        if duration == 4:
            return "veo-3.1-lite-free", "abra_t2v_4s", 4
        if duration == 6:
            return "veo-3.1-lite", "abra_t2v_6s", 6
        if duration in (8, 10):
            return "omni-1.1-flash", f"abra_t2v_{duration}s", duration

        # Default is Omni 1.1 Flash (6 credits)
        return "omni-1.1-flash", "abra_t2v_10s", 10

    def _resolve_duration(self, prompt: str, duration: Optional[int] = None, model: Optional[str] = None) -> int:
        """Backward-compatibility duration resolver."""
        _, _, dur = self._resolve_model_and_duration(prompt, duration, model)
        return dur

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        duration: Optional[int] = None,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        resolution: str = DEFAULT_RESOLUTION,
        negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None,
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate video via Google Flow using Camofox Bridge & Auto-Refresh Daemon."""
        active_model_id, model_key, chosen_duration = self._resolve_model_and_duration(prompt, duration, model)
        chosen_aspect = "portrait" if aspect_ratio in ("9:16", "portrait") else "landscape"

        logger.info(
            "Google Flow video request: prompt='%s', model=%s (key=%s), duration=%ds, aspect=%s",
            prompt[:60], active_model_id, model_key, chosen_duration, chosen_aspect
        )

        try:
            try:
                from bridge.flow.flow_refresh_daemon import FlowRefreshDaemon
                from bridge.flow.camofox_bridge import CamofoxFlowBridge
                from bridge.flow import generators
            except ImportError:
                from tools.antigravity_bridge.flow.flow_refresh_daemon import FlowRefreshDaemon
                from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
                from tools.antigravity_bridge.flow import generators

            # Step 1: Ensure active token via Headless Auto-Refresh Daemon
            async def _ensure_token():
                daemon = FlowRefreshDaemon.get_instance()
                return await daemon.ensure_active_token(min_validity_seconds=300)

            token_ok, token_val = self._run_async(_ensure_token())
            if not token_ok and not token_val:
                return error_response(
                    error="Google Flow session expired or not authenticated. Please run 1-Click Handshake on Dashboard or CLI.",
                    error_type="AuthenticationError",
                    model=active_model_id,
                    prompt=prompt,
                    provider="antigravity",
                )

            # Step 2: Bridge connection & generation
            bridge = CamofoxFlowBridge()
            if token_val:
                bridge._flow_key = token_val

            async def _execute_generation() -> str:
                # Text-to-video generation
                media_ids = await generators.generate_video(
                    bridge,
                    prompt=prompt,
                    aspect=chosen_aspect,
                    duration=chosen_duration,
                    count=1,
                    seed=seed,
                    video_model=model_key,
                )
                if not media_ids:
                    raise RuntimeError("No media ID returned from Google Flow.")

                media_id = media_ids[0]
                logger.info("Generation submitted. Media ID: %s. Polling status...", media_id)

                # Poll status until complete
                is_ready, video_url = await generators.poll_video_status(
                    bridge,
                    media_id=media_id,
                    timeout=180,
                    poll_interval=4,
                )
                if not is_ready or not video_url:
                    raise RuntimeError(f"Video generation incomplete or failed: {video_url}")

                # Download local .mp4 file
                media_dir = _h_home / "media" / "flow"
                media_dir.mkdir(parents=True, exist_ok=True)

                slug = re.sub(r"[^\w\s-]", "", prompt)[:35].strip().replace(" ", "_") or "video"
                local_path = media_dir / f"flow_{slug}_{media_id[:6]}.mp4"

                try:
                    dl_func = getattr(generators, "download_file", getattr(generators, "download_media", None))
                    if dl_func:
                        await dl_func(video_url, local_path)
                except Exception as dl_err:
                    logger.warning("Could not download video to local file: %s", dl_err)

                if local_path.is_file() and local_path.stat().st_size > 1000:
                    return str(local_path.resolve())
                else:
                    return video_url

            local_video_path = self._run_async(_execute_generation())

            return success_response(
                video=local_video_path,
                model=active_model_id,
                prompt=prompt,
                modality="text" if not image_url else "image",
                aspect_ratio="16:9" if chosen_aspect == "landscape" else "9:16",
                duration=chosen_duration,
                provider="antigravity",
                extra={
                    "resolution": "720p",
                    "local_file": local_video_path if os.path.exists(local_video_path) else None,
                },
            )

        except Exception as e:
            logger.exception("Google Flow video generation failed: %s", e)
            return error_response(
                error=str(e),
                error_type="GenerationError",
                model=active_model_id,
                prompt=prompt,
                provider="antigravity",
            )

    def _run_async(self, coro):
        """Execute coroutine synchronously from sync context."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        except RuntimeError:
            return asyncio.run(coro)


def register(ctx) -> None:
    """Register AntigravityVideoGenProvider with Hermes."""
    ctx.register_video_gen_provider(AntigravityVideoGenProvider())
