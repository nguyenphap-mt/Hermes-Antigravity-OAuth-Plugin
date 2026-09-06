"""Hermes Agent tool registration for Google Flow.

Registers tools that the AI agent can call to generate video, images,
and upsample video through Google Flow via Camofox.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

try:
    from tools.antigravity_bridge.flow.automation import (
        GoogleFlowClient,
        FlowResult,
        DEFAULT_MEDIA_DIR,
    )
except ImportError:
    try:
        from bridge.flow.automation import (
            GoogleFlowClient,
            FlowResult,
            DEFAULT_MEDIA_DIR,
        )
    except ImportError:
        try:
            from flow.automation import (
                GoogleFlowClient,
                FlowResult,
                DEFAULT_MEDIA_DIR,
            )
        except ImportError:
            from .automation import (
                GoogleFlowClient,
                FlowResult,
                DEFAULT_MEDIA_DIR,
            )

logger = logging.getLogger("tools.antigravity_bridge.flow.tools")

# Global client instance
_flow_client: Optional[GoogleFlowClient] = None
_flow_client_lock = asyncio.Lock()


async def _get_or_create_client(headless: bool = True) -> GoogleFlowClient:
    """Get existing Flow client or create a new one."""
    global _flow_client

    async with _flow_client_lock:
        if _flow_client is None:
            _flow_client = GoogleFlowClient(headless=headless)
            await _flow_client.start()

        return _flow_client


async def _shutdown_client() -> None:
    """Shutdown the global Flow client."""
    global _flow_client
    if _flow_client:
        await _flow_client.close()
        _flow_client = None


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# =============================================================================
# Tool Functions
# =============================================================================

def google_flow_video(
    prompt: str,
    style: str = "",
    duration: int = 10,
    aspect_ratio: str = "16:9",
) -> dict:
    """Generate a video using Google Flow AI.

    Creates a cinematic video from a text prompt using Google's
    advanced generative models (veo / abra) via Google Flow.

    Args:
        prompt: Description of the video to generate.
        style: Optional style preset (e.g. cinematic, anime, realistic).
        duration: Video duration in seconds (4, 6, 8, 10). Default is 10.
        aspect_ratio: Aspect ratio ("16:9" or "9:16"). Default is "16:9".

    Returns:
        Dict with file_path, flow_url, media_id, duration_seconds.
    """
    async def _gen():
        client = await _get_or_create_client()
        return await client.generate_video(prompt, style=style, duration=duration, aspect_ratio=aspect_ratio)

    result = _run_async(_gen())
    return _format_result(result)


def google_flow_image(
    prompt: str,
    style: str = "",
    aspect_ratio: str = "16:9",
    model: str = "narwhal",
    count: int = 1,
    ref_images: Optional[List[str]] = None,
) -> dict:
    """Generate high-quality images using Google Flow AI.

    Args:
        prompt: Description of the image.
        style: Optional style preset.
        aspect_ratio: "16:9", "9:16", "1:1", "4:3", or "3:4". Default: "16:9".
        model: "narwhal" (standard), "harbor_seal" (lite), or "gem_pix_2" (pro).
        count: Number of images to generate (1 to 4). Default: 1.
        ref_images: Optional reference image media IDs.

    Returns:
        Dict with file_path, flow_url, media_id, and metadata.
    """
    async def _gen():
        client = await _get_or_create_client()
        return await client.generate_image(
            prompt, style=style, aspect_ratio=aspect_ratio, model=model, count=count, ref_images=ref_images
        )

    result = _run_async(_gen())
    return _format_result(result)


def google_flow_upsample(
    media_id: str,
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
) -> dict:
    """Upsample an existing Google Flow video to 1080p or 4K.

    Args:
        media_id: The media ID of the generated video to upsample.
        resolution: Target resolution ("1080p" or "4k"). Default: "1080p".
        aspect_ratio: Video aspect ratio ("16:9" or "9:16"). Default: "16:9".

    Returns:
        Dict with file_path, flow_url, and media_id of the upsampled video.
    """
    async def _up():
        client = await _get_or_create_client()
        return await client.upsample_video(media_id=media_id, resolution=resolution, aspect_ratio=aspect_ratio)

    result = _run_async(_up())
    return _format_result(result)


def google_flow_status() -> dict:
    """Check readiness of Camofox and Google Flow session.

    Returns:
        Dict with server_running, tab_connected, logged_in status.
    """
    async def _stat():
        client = await _get_or_create_client()
        return await client.check_status()

    return _run_async(_stat())


def google_flow_accounts() -> dict:
    """List and inspect all registered accounts in the Google Flow pool."""
    async def _list():
        client = await _get_or_create_client()
        accounts = client.pool.list_accounts()
        active_acc = client.pool.get_active_account()
        return {
            "active_account_id": active_acc.id,
            "active_account_email": active_acc.email,
            "total_accounts": len(accounts),
            "accounts": [a.to_dict() for a in accounts],
        }

    return _run_async(_list())


def google_flow_login(account_id: str = "default", label: str = "", timeout: int = 180) -> dict:
    """Trigger interactive login on Google Flow via Camofox desktop browser.

    Args:
        account_id: Target account ID to log into (default: 'default').
        label: Human-readable label for this account.
        timeout: Maximum seconds to wait for user to log in (default: 180).

    Returns:
        Dict indicating whether login was successful.
    """
    async def _login():
        client = await _get_or_create_client()
        acc = client.pool.add_or_update_account(account_id, label=label)
        client.pool.set_active_account(acc.id)
        await client.bridge.switch_user(acc.user_id)

        ok = await client.interactive_login(timeout=timeout)
        if ok:
            status = await client.check_status()
            return {
                "success": True,
                "account_id": acc.id,
                "email": status.get("email") or acc.email,
                "message": f"Logged into Google Flow successfully as account '{acc.id}'!",
            }
        return {"success": False, "account_id": acc.id, "message": "Login timed out."}

    return _run_async(_login())


def _format_result(result: FlowResult) -> dict:
    """Format FlowResult into tool response dict."""
    response = result.to_dict()

    if result.success and result.file_path:
        response["message"] = (
            f"✅ {result.media_type.title()} generated successfully!\n"
            f"📁 File: {result.file_path}\n"
            f"🆔 Media ID: {result.media_id or 'N/A'}\n"
            f"⏱️ Time: {result.duration_seconds:.1f}s"
        )
        if result.flow_url:
            response["message"] += f"\n🔗 Flow URL: {result.flow_url}"
    else:
        response["message"] = f"❌ Generation failed: {result.error}"

    return response


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_flow_tools():
    """Register Google Flow tools with Hermes tool system."""
    try:
        from tools.registry import register

        register(
            name="google_flow_video",
            func=google_flow_video,
            description="Generate a video using Google Flow AI (supports 4s, 6s, 8s, 10s).",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text prompt for video"},
                    "style": {"type": "string", "description": "Style preset (cinematic, anime, etc.)", "default": ""},
                    "duration": {"type": "integer", "description": "Duration in seconds (4, 6, 8, 10)", "default": 10},
                    "aspect_ratio": {"type": "string", "description": "16:9 or 9:16", "default": "16:9"},
                },
                "required": ["prompt"],
            },
            toolset="google_flow",
        )

        register(
            name="google_flow_image",
            func=google_flow_image,
            description="Generate an image using Google Flow AI (models: narwhal, harbor_seal, gem_pix_2).",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text prompt for image"},
                    "style": {"type": "string", "description": "Optional style preset", "default": ""},
                    "aspect_ratio": {"type": "string", "description": "16:9, 9:16, 1:1, 4:3, 3:4", "default": "16:9"},
                    "model": {"type": "string", "description": "narwhal, harbor_seal, gem_pix_2", "default": "narwhal"},
                    "count": {"type": "integer", "description": "1-4 images", "default": 1},
                },
                "required": ["prompt"],
            },
            toolset="google_flow",
        )

        register(
            name="google_flow_upsample",
            func=google_flow_upsample,
            description="Upsample an existing Google Flow video to 1080p or 4K.",
            parameters={
                "type": "object",
                "properties": {
                    "media_id": {"type": "string", "description": "Media ID of video"},
                    "resolution": {"type": "string", "description": "1080p or 4k", "default": "1080p"},
                    "aspect_ratio": {"type": "string", "description": "16:9 or 9:16", "default": "16:9"},
                },
                "required": ["media_id"],
            },
            toolset="google_flow",
        )

        register(
            name="google_flow_accounts",
            func=google_flow_accounts,
            description="Inspect all accounts in the Google Flow multi-account pool and view their credit/exhaustion status.",
            parameters={"type": "object", "properties": {}},
            toolset="google_flow",
        )

        register(
            name="google_flow_status",
            func=google_flow_status,
            description="Check readiness of Camofox and Google Flow session.",
            parameters={"type": "object", "properties": {}},
            toolset="google_flow",
        )

        register(
            name="google_flow_login",
            func=google_flow_login,
            description="Open Camofox desktop browser window to log in to Google Flow with a specific account.",
            parameters={
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "Optional account identifier (e.g. 'default', 'acc_2', 'work'). Default is 'default'.",
                        "default": "default",
                    },
                    "label": {
                        "type": "string",
                        "description": "Optional human-readable label for this account.",
                    },
                    "timeout": {"type": "integer", "description": "Max seconds to wait", "default": 180},
                },
            },
            toolset="google_flow",
        )

        logger.info("Google Flow tools registered successfully.")
    except Exception as e:
        logger.debug("Could not register Google Flow tools: %s", e)
