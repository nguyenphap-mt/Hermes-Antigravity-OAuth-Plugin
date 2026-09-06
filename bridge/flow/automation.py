"""Google Flow Automation Client.

Integrates CamofoxFlowBridge with Flow Engine Generators (ported from
kodelyx/flow-agent) to provide full-featured, anti-detect Google Flow image
and video generation in Hermes Agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .camofox_bridge import CamofoxFlowBridge
    from . import generators
    from .account_pool import FlowAccountPoolManager, FlowAccount
    from .generators import FlowCreditExhaustedError
except (ImportError, ValueError):
    try:
        from bridge.flow.camofox_bridge import CamofoxFlowBridge
        from bridge.flow import generators
        from bridge.flow.account_pool import FlowAccountPoolManager, FlowAccount
        from bridge.flow.generators import FlowCreditExhaustedError
    except ImportError:
        try:
            from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
            from tools.antigravity_bridge.flow import generators
            from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager, FlowAccount
            from tools.antigravity_bridge.flow.generators import FlowCreditExhaustedError
        except ImportError:
            from flow.camofox_bridge import CamofoxFlowBridge
            from flow import generators
            from flow.account_pool import FlowAccountPoolManager, FlowAccount
            from flow.generators import FlowCreditExhaustedError

logger = logging.getLogger("tools.antigravity_bridge.flow.automation")

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MEDIA_DIR = Path.home() / ".hermes" / "media" / "flow"


@dataclass
class FlowResult:
    """Result from a Google Flow generation request."""

    success: bool
    file_path: Optional[str] = None        # Local path after download
    flow_url: Optional[str] = None         # Direct URL or Link on Google Flow
    media_type: str = "unknown"            # "video" | "image" | "audio"
    prompt: str = ""
    duration_seconds: float = 0.0          # Time taken to generate
    error: Optional[str] = None
    media_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "file_path": self.file_path,
            "flow_url": self.flow_url,
            "media_type": self.media_type,
            "prompt": self.prompt,
            "duration_seconds": round(self.duration_seconds, 1),
            "media_id": self.media_id,
            "error": self.error,
            "metadata": self.metadata,
        }


class GoogleFlowClient:
    """High-level client for Google Flow using Camofox & Flow Generators."""

    def __init__(
        self,
        access_token: str = "",
        email: str = "",
        headless: bool = True,
        media_dir: Optional[Path] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        user_data_dir: Optional[Path] = None,
    ):
        self.access_token = access_token
        self.email = email
        self.headless = headless
        self.media_dir = media_dir or DEFAULT_MEDIA_DIR
        self.timeout = timeout
        self.user_data_dir = user_data_dir
        self.media_dir.mkdir(parents=True, exist_ok=True)

        # Backwards compatibility attributes
        self._is_logged_in = False
        self._is_started = False
        self._lock = asyncio.Lock()

        # Initialize Account Pool & Camofox bridge
        self.pool = FlowAccountPoolManager()
        active_acc = self.pool.get_active_account()
        self.bridge = CamofoxFlowBridge(user_id=active_acc.user_id, command_timeout=45)

    async def _execute_with_failover(self, op_name: str, coro_fn):
        """Execute generator operation with automatic account failover on credit exhaustion."""
        accounts = self.pool.list_accounts()
        max_attempts = max(1, len(accounts))

        for attempt in range(max_attempts):
            active_acc = self.pool.get_active_account()
            await self.bridge.switch_user(active_acc.user_id)

            try:
                result = await coro_fn()
                self.pool.record_success(active_acc.id)
                return result
            except Exception as e:
                err_str = str(e).lower()
                is_exhausted = (
                    isinstance(e, FlowCreditExhaustedError)
                    or getattr(e, "status_code", 0) in (429, 402)
                    or any(k in err_str for k in ("quota", "credit", "exhausted", "rate limit", "429"))
                )
                if not is_exhausted:
                    raise

                logger.warning(
                    "[FlowPool] Account '%s' (%s) credit exhausted during %s: %s",
                    active_acc.id,
                    active_acc.email or active_acc.label,
                    op_name,
                    e,
                )
                next_acc = self.pool.mark_account_exhausted(active_acc.id)
                if next_acc:
                    logger.info(
                        "[FlowPool] Auto-Failover: Switched from '%s' to '%s'. Retrying %s...",
                        active_acc.id,
                        next_acc.id,
                        op_name,
                    )
                    continue
                else:
                    raise RuntimeError(
                        f"All Google Flow accounts in the pool are exhausted or on cooldown! "
                        f"Last error: {e}. Please add another account via 'python manage.py flow-login --account <name>'."
                    )

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self) -> None:
        """Ensure Camofox server is active and tab is ready."""
        if self._is_started:
            return

        async with self._lock:
            # Auto-start server if not running
            if not self.bridge.is_server_running():
                logger.info("Camofox server not running. Auto-starting...")
                self.bridge.ensure_server()

            await self.bridge.ensure_tab()
            self._is_started = True

    async def close(self) -> None:
        """Close client resources."""
        self._is_started = False

    async def check_status(self) -> Dict[str, Any]:
        """Check readiness of Camofox and Flow session."""
        active_acc = self.pool.get_active_account()
        if self.bridge.user_id != active_acc.user_id:
            await self.bridge.switch_user(active_acc.user_id)
        status = await self.bridge.check_status()
        self._is_logged_in = status.get("logged_in", False)

        # Auto-sync detected email to account pool
        email = status.get("email")
        if email and email != active_acc.email:
            self.pool.add_or_update_account(active_acc.id, email=email)

        status["active_account"] = active_acc.to_dict()
        status["total_accounts"] = len(self.pool.list_accounts())
        return status

    # ─── Image Generation ───────────────────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        style: str = "",
        aspect_ratio: str = "16:9",
        model: str = "narwhal",
        count: int = 1,
        ref_images: Optional[List[str]] = None,
    ) -> FlowResult:
        """Generate images using Google Flow.

        Args:
            prompt: Text description of image.
            style: Optional style prompt prefix.
            aspect_ratio: Aspect ratio ("16:9", "9:16", "1:1", "4:3", "3:4").
            model: Image model ("narwhal", "harbor_seal", "gem_pix_2").
            count: Variations count (1 to 4).
            ref_images: Optional list of reference image media IDs.
        """
        await self.start()
        full_prompt = f"{style} {prompt}".strip() if style else prompt
        start_time = time.time()

        try:
            async def _do_gen_img():
                return await generators.generate_image(
                    self.bridge,
                    prompt=full_prompt,
                    aspect=aspect_ratio,
                    model=model,
                    count=count,
                    ref_media_ids=ref_images,
                )

            results = await self._execute_with_failover("Image Generation", _do_gen_img)

            if not results:
                return FlowResult(
                    success=False,
                    prompt=prompt,
                    error="No images returned by Google Flow",
                    duration_seconds=time.time() - start_time,
                )

            primary = results[0]
            media_id = primary.get("media_id")
            image_url = primary.get("image_url")

            # Download primary image
            safe_slug = "".join(c if c.isalnum() or c in " _-" else "" for c in prompt)[:40].strip() or "image"
            output_file = self.media_dir / f"flow_{safe_slug}_{uuid.uuid4().hex[:6]}.png"

            if image_url:
                await generators.download_file(image_url, output_file)

            return FlowResult(
                success=True,
                file_path=str(output_file) if output_file.exists() else None,
                flow_url=image_url,
                media_type="image",
                prompt=prompt,
                duration_seconds=time.time() - start_time,
                media_id=media_id,
                metadata={"variations": results, "model": model, "aspect": aspect_ratio},
            )
        except Exception as e:
            logger.error("Image generation error: %s", e)
            return FlowResult(
                success=False,
                prompt=prompt,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    # ─── Video Generation ───────────────────────────────────────────────

    async def generate_video(
        self,
        prompt: str,
        style: str = "",
        duration: int = 10,
        aspect_ratio: str = "16:9",
    ) -> FlowResult:
        """Generate video using Google Flow.

        Args:
            prompt: Text description of video.
            style: Optional style description.
            duration: Video duration in seconds (4, 6, 8, 10).
            aspect_ratio: Video aspect ratio ("16:9", "9:16").
        """
        await self.start()
        full_prompt = f"{style} {prompt}".strip() if style else prompt
        start_time = time.time()

        try:
            # 1. Submit T2V request with auto-failover
            async def _do_gen_vid():
                return await generators.generate_video(
                    self.bridge,
                    prompt=full_prompt,
                    aspect=aspect_ratio,
                    duration=duration,
                )

            media_ids = await self._execute_with_failover("Video Generation", _do_gen_vid)
            if not media_ids:
                return FlowResult(
                    success=False,
                    prompt=prompt,
                    error="Failed to submit video generation job",
                    duration_seconds=time.time() - start_time,
                )

            media_id = media_ids[0]

            # 2. Poll until ready
            is_ready, video_url_or_err = await generators.poll_video_status(
                self.bridge, media_id=media_id, timeout=self.timeout
            )
            if not is_ready:
                return FlowResult(
                    success=False,
                    prompt=prompt,
                    error=f"Video generation polling failed: {video_url_or_err}",
                    media_id=media_id,
                    duration_seconds=time.time() - start_time,
                )

            video_url = video_url_or_err
            safe_slug = "".join(c if c.isalnum() or c in " _-" else "" for c in prompt)[:40].strip() or "video"
            output_file = self.media_dir / f"flow_{safe_slug}_{uuid.uuid4().hex[:6]}.mp4"

            if video_url:
                await generators.download_file(video_url, output_file)

            return FlowResult(
                success=True,
                file_path=str(output_file) if output_file.exists() else None,
                flow_url=video_url,
                media_type="video",
                prompt=prompt,
                duration_seconds=time.time() - start_time,
                media_id=media_id,
                metadata={"duration": duration, "aspect": aspect_ratio},
            )
        except Exception as e:
            logger.error("Video generation error: %s", e)
            return FlowResult(
                success=False,
                prompt=prompt,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    # ─── Upsample Video ─────────────────────────────────────────────────

    async def upsample_video(
        self,
        media_id: str,
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
    ) -> FlowResult:
        """Upsample an existing video to 1080p or 4K."""
        await self.start()
        start_time = time.time()

        try:
            async def _do_upsample():
                return await generators.upsample_video(
                    self.bridge,
                    media_id=media_id,
                    resolution=resolution,
                    aspect=aspect_ratio,
                )

            upsampled_ids = await self._execute_with_failover("Video Upsample", _do_upsample)
            if not upsampled_ids:
                return FlowResult(
                    success=False,
                    error="Failed to submit video upsample job",
                    duration_seconds=time.time() - start_time,
                )

            new_media_id = upsampled_ids[0]
            is_ready, video_url_or_err = await generators.poll_video_status(
                self.bridge, media_id=new_media_id, timeout=self.timeout
            )
            if not is_ready:
                return FlowResult(
                    success=False,
                    error=f"Upsample polling failed: {video_url_or_err}",
                    media_id=new_media_id,
                    duration_seconds=time.time() - start_time,
                )

            video_url = video_url_or_err
            output_file = self.media_dir / f"flow_upsampled_{resolution}_{uuid.uuid4().hex[:6]}.mp4"
            if video_url:
                await generators.download_file(video_url, output_file)

            return FlowResult(
                success=True,
                file_path=str(output_file) if output_file.exists() else None,
                flow_url=video_url,
                media_type="video",
                duration_seconds=time.time() - start_time,
                media_id=new_media_id,
                metadata={"resolution": resolution, "source_media_id": media_id},
            )
        except Exception as e:
            logger.error("Upsample error: %s", e)
            return FlowResult(
                success=False,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    # ─── Gallery & Creations ───────────────────────────────────────────

    async def list_creations(self) -> List[Dict[str, Any]]:
        """List local and remote creations."""
        creations = []
        if self.media_dir.exists():
            for f in sorted(self.media_dir.glob("flow_*"), key=os.path.getmtime, reverse=True)[:50]:
                creations.append({
                    "name": f.name,
                    "file_path": str(f),
                    "media_type": "video" if f.suffix == ".mp4" else "image",
                    "created_at": os.path.getmtime(f),
                })
        return creations

    async def generate_music(self, prompt: str, duration: int = 30) -> FlowResult:
        """Generate music (placeholder for MusicFX)."""
        return FlowResult(
            success=False,
            prompt=prompt,
            error="Music generation via Flow is currently not supported by this API endpoint.",
            media_type="audio",
        )

    # ─── Interactive Login ──────────────────────────────────────────────

    async def interactive_login(self, timeout: int = 180) -> bool:
        """Ensure Camofox server runs with interactive desktop for Google login."""
        self.bridge.ensure_server(interactive_mode="desktop")
        await self.bridge.ensure_tab()
        await self.bridge.navigate("https://labs.google/fx/tools/flow")

        logger.info("Interactive login window requested. Waiting for user login...")
        start = time.time()
        while time.time() - start < timeout:
            status = await self.check_status()
            if status.get("logged_in"):
                logger.info("Google Flow login successful!")
                self._is_logged_in = True
                return True
            await asyncio.sleep(2)

        return False
