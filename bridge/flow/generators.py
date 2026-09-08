"""Flow Engine — Generators.

Ported from kodelyx/flow-agent (generators/t2i, t2v, i2v, upsample, common).
Contains all high-level generation, polling, and media downloading logic.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
import re
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("tools.antigravity_bridge.flow.generators")

DEFAULT_PROJECT = os.environ.get("DEFAULT_PROJECT", "0143adf4-5864-4cb4-abb5-fe4254ad0dc7")
_FLOW_PUBLIC_KEY_B64 = "QUl6YVN5QnRybTBvNWFiMWMtRWM4WnVMY0d0M29KQUE1Vld0M3BZ"


def _get_flow_public_api_key() -> str:
    return os.environ.get("GOOGLE_FLOW_API_KEY") or base64.b64decode(_FLOW_PUBLIC_KEY_B64).decode("utf-8")


class FlowCreditExhaustedError(RuntimeError):
    """Raised when Google Flow credits or quota are exhausted on the active account."""

    def __init__(self, message: str, status_code: int = 429, raw_response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response or {}


def _check_flow_error(result: dict, operation_name: str) -> None:
    """Check API result and raise FlowCreditExhaustedError or RuntimeError appropriately."""
    status = result.get("status", 200)
    if status == 200:
        return

    data_err = result.get("data", {}).get("error", {})
    err_msg = str(data_err.get("message") or result.get("error") or f"HTTP {status}")

    # Detect quota / credit exhaustion patterns
    is_exhausted = (
        status in (429, 402)
        or any(kw in err_msg.lower() for kw in (
            "quota", "credit", "exhausted", "resource_exhausted",
            "limit reached", "rate limit", "insufficient", "try again later",
            "paygate", "credits"
        ))
    )
    if is_exhausted:
        raise FlowCreditExhaustedError(
            f"Google Flow credit/quota exhausted during {operation_name}: {err_msg}",
            status_code=status,
            raw_response=result,
        )
    raise RuntimeError(f"Flow {operation_name} failed: {err_msg}")

IMAGE_MODELS = {
    "harbor_seal": "HARBOR_SEAL",
    "lite": "HARBOR_SEAL",
    "narwhal": "NARWHAL",
    "nano_banana": "NARWHAL",
    "standard": "NARWHAL",
    "gem_pix_2": "GEM_PIX_2",
    "pro": "GEM_PIX_2",
}
DEFAULT_IMAGE_MODEL = "NARWHAL"

IMAGE_ASPECTS = {
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",   # 16:9
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",     # 9:16
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "square": "IMAGE_ASPECT_RATIO_SQUARE",         # 1:1
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
    "4:3": "IMAGE_ASPECT_RATIO_4_3",
    "4x3": "IMAGE_ASPECT_RATIO_4_3",
    "3:4": "IMAGE_ASPECT_RATIO_3_4",
    "3x4": "IMAGE_ASPECT_RATIO_3_4",
}

VIDEO_ASPECTS = {
    "landscape": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "portrait": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "9:16": "VIDEO_ASPECT_RATIO_PORTRAIT",
}

VIDEO_MODELS = {
    4: "abra_t2v_4s",
    6: "abra_t2v_6s",
    8: "abra_t2v_8s",
    10: "abra_t2v_10s",
}

VIDEO_UPSAMPLE_MODELS = {
    "1080p": "veo_3_1_upsampler_1080p",
    "4k": "veo_3_1_upsampler_4k",
}

VIDEO_UPSAMPLE_RESOLUTIONS = {
    "1080p": "VIDEO_RESOLUTION_1080P",
    "4k": "VIDEO_RESOLUTION_4K",
}

ENDPOINTS = {
    "generate_t2v": "/v1/video:batchAsyncGenerateVideoText",
    "generate_i2v": "/v1/video:batchAsyncGenerateVideoStartImage",
    "generate_fl": "/v1/video:batchAsyncGenerateVideoStartAndEndImage",
    "generate_r2v": "/v1/video:batchAsyncGenerateVideoReferenceImages",
    "generate_edit": "/v1/video:batchAsyncGenerateVideoEditVideo",
    "upload_image": "/v1/flow/uploadImage",
    "upsample_video": "/v1/video:batchAsyncGenerateVideoUpsampleVideo",
    "poll_status": "/v1/video:batchCheckAsyncVideoGenerationStatus",
    "get_media": "/v1/flowMedia/{media_id}",
    "get_credits": "/v1/credits",
}

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def extract_media_id(name_or_uri: str) -> str:
    """Extract clean UUID media_id from resource name or URL."""
    if not name_or_uri:
        return ""
    m = UUID_RE.search(name_or_uri)
    return m.group() if m else ""


def resolve_seed(seed: Optional[int], index: int = 0) -> int:
    """Resolve seed for generation item."""
    if seed is None:
        return random.randint(1, 999999)
    return (int(seed) + index) % 4294967296


def build_client_context(project_id: str) -> dict:
    """Build clientContext used by Flow API requests."""
    return {
        "projectId": project_id,
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_ONE",
        "sessionId": f";{int(time.time() * 1000)}",
        "recaptchaContext": {
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            "token": "",
        },
    }


def build_generation_context(audio_pref: str = None) -> dict:
    """Build mediaGenerationContext dict."""
    ctx = {"batchId": str(uuid.uuid4())}
    if audio_pref:
        ctx["audioFailurePreference"] = audio_pref
    return ctx


# ─── Image Generation ───────────────────────────────────────────────

def _parse_image_results(data: dict) -> List[Dict[str, str]]:
    """Parse media results from batchGenerateImages response."""
    results = []
    media_list = data.get("media", [])

    for item in media_list:
        r = {"media_id": "", "image_url": ""}
        name = item.get("name", "")
        if name:
            r["media_id"] = extract_media_id(name)

        img = item.get("image", {})
        gen = img.get("generatedImage", {})
        url = gen.get("fifeUrl", "") or gen.get("imageUri", "")
        if url:
            r["image_url"] = url
            if not r["media_id"]:
                r["media_id"] = extract_media_id(url)

        if not r["media_id"] and name:
            r["media_id"] = name

        if r["image_url"]:
            results.append(r)

    return results


async def generate_image(
    bridge,
    prompt: str,
    aspect: str = "landscape",
    model: str = "narwhal",
    count: int = 1,
    seed: Optional[int] = None,
    ref_media_ids: Optional[List[str]] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Generate image variations from text prompt."""
    project_id = project_id or DEFAULT_PROJECT
    count = max(1, min(4, count))
    aspect_enum = IMAGE_ASPECTS.get(aspect.lower(), "IMAGE_ASPECT_RATIO_LANDSCAPE")
    target_model = IMAGE_MODELS.get((model or "").lower(), DEFAULT_IMAGE_MODEL)

    requests = []
    ts = int(time.time() * 1000)
    for i in range(count):
        req_item = {
            "clientContext": build_client_context(project_id),
            "seed": resolve_seed(seed, i),
            "structuredPrompt": {"parts": [{"text": prompt}]},
            "imageAspectRatio": aspect_enum,
            "imageModelName": target_model,
        }
        if ref_media_ids:
            req_item["imageInputs"] = [
                {"name": mid, "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"}
                for mid in ref_media_ids
            ]
        requests.append(req_item)

    body = {
        "clientContext": build_client_context(project_id),
        "requests": requests,
    }
    if ref_media_ids:
        body["mediaGenerationContext"] = build_generation_context()
        body["useNewMedia"] = True

    try:
        from bridge.flow.flow_refresh_daemon import ensure_flow_token
        ok, tok = await ensure_flow_token()
        if ok and tok:
            bridge._flow_key = tok
    except Exception as ref_err:
        logger.debug("Token pre-check warning: %s", ref_err)

    endpoint = f"/v1/projects/{project_id}/flowMedia:batchGenerateImages"
    logger.info("Generating Image: '%s' [%s] model=%s x%d", prompt[:60], aspect, target_model, count)

    result = await bridge.api_request(endpoint, body, captcha_action="IMAGE_GENERATION")
    _check_flow_error(result, "Image Generation")

    data = result.get("data", {})
    results = _parse_image_results(data)
    if not results:
        raise RuntimeError("No images returned in Flow API response.")

    return results


# ─── Video Generation ───────────────────────────────────────────────

async def generate_video(
    bridge,
    prompt: str,
    aspect: str = "landscape",
    duration: int = 10,
    count: int = 1,
    seed: Optional[int] = None,
    project_id: Optional[str] = None,
    video_model: Optional[str] = None,
) -> List[str]:
    """Submit Text-to-Video generation request. Returns media IDs."""
    project_id = project_id or DEFAULT_PROJECT
    aspect_enum = VIDEO_ASPECTS.get(aspect.lower(), "VIDEO_ASPECT_RATIO_LANDSCAPE")
    model_key = video_model or VIDEO_MODELS.get(duration, "abra_t2v_10s")

    requests = []
    for i in range(count):
        requests.append({
            "aspectRatio": aspect_enum,
            "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
            "videoModelKey": model_key,
            "seed": resolve_seed(seed, i),
            "metadata": {},
        })

    body = {
        "mediaGenerationContext": build_generation_context(),
        "clientContext": build_client_context(project_id),
        "requests": requests,
        "useV2ModelConfig": True,
    }

    try:
        from bridge.flow.flow_refresh_daemon import ensure_flow_token
        ok, tok = await ensure_flow_token()
        if ok and tok:
            bridge._flow_key = tok
    except Exception as ref_err:
        logger.debug("Token pre-check warning: %s", ref_err)

    logger.info("Generating Video: '%s' [%s] %ds x%d", prompt[:60], aspect, duration, count)
    result = await bridge.api_request(ENDPOINTS["generate_t2v"], body, captcha_action="VIDEO_GENERATION")
    _check_flow_error(result, "Video Generation")

    data = result.get("data", {})
    media = data.get("media", [])
    if not media:
        raise RuntimeError("No media returned in Flow video response.")

    media_ids = [extract_media_id(m.get("name", "")) or m.get("name", "") for m in media if m.get("name")]
    logger.info("Submitted video job successfully! Media IDs: %s", media_ids)
    return media_ids


async def generate_i2v(
    bridge,
    prompt: str,
    start_image_media_id: str,
    aspect: str = "landscape",
    duration: int = 10,
    seed: Optional[int] = None,
    project_id: Optional[str] = None,
) -> List[str]:
    """Generate video starting from an image (Image-to-Video)."""
    project_id = project_id or DEFAULT_PROJECT
    aspect_enum = VIDEO_ASPECTS.get(aspect.lower(), "VIDEO_ASPECT_RATIO_LANDSCAPE")
    model_key = VIDEO_MODELS.get(duration, "abra_t2v_10s")

    requests = [{
        "aspectRatio": aspect_enum,
        "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
        "videoModelKey": model_key,
        "seed": resolve_seed(seed),
        "videoInput": {"startImage": {"mediaId": start_image_media_id}},
        "metadata": {},
    }]

    body = {
        "mediaGenerationContext": build_generation_context(),
        "clientContext": build_client_context(project_id),
        "requests": requests,
        "useV2ModelConfig": True,
    }

    logger.info("Generating I2V Video: '%s' starting from media %s", prompt[:60], start_image_media_id)
    result = await bridge.api_request(ENDPOINTS["generate_i2v"], body, captcha_action="VIDEO_GENERATION")
    _check_flow_error(result, "I2V Generation")

    data = result.get("data", {})
    media = data.get("media", [])
    return [extract_media_id(m.get("name", "")) for m in media if m.get("name")]


async def upsample_video(
    bridge,
    media_id: str,
    resolution: str = "1080p",
    aspect: str = "landscape",
    project_id: Optional[str] = None,
) -> List[str]:
    """Upsample existing video to 1080p or 4K."""
    project_id = project_id or DEFAULT_PROJECT
    tier = "4k" if "4k" in resolution.lower() or "2160" in resolution.lower() else "1080p"
    model_key = VIDEO_UPSAMPLE_MODELS[tier]
    res_enum = VIDEO_UPSAMPLE_RESOLUTIONS[tier]
    aspect_enum = VIDEO_ASPECTS.get(aspect.lower(), "VIDEO_ASPECT_RATIO_LANDSCAPE")

    body = {
        "mediaGenerationContext": build_generation_context(),
        "clientContext": build_client_context(project_id),
        "requests": [{
            "aspectRatio": aspect_enum,
            "videoModelKey": model_key,
            "videoInput": {"mediaId": media_id},
            "resolution": res_enum,
        }],
    }

    logger.info("Upsampling video %s to %s (%s)", media_id, tier, model_key)
    result = await bridge.api_request(ENDPOINTS["upsample_video"], body, captcha_action="VIDEO_GENERATION")
    _check_flow_error(result, "Video Upsample")

    data = result.get("data", {})
    media = data.get("media", [])
    return [extract_media_id(m.get("name", "")) or m.get("name", "") for m in media if m.get("name")]


# ─── Status Polling & Media Download ────────────────────────────────

async def poll_video_status(
    bridge,
    media_id: str,
    project_id: Optional[str] = None,
    timeout: int = 360,
    poll_interval: int = 5,
) -> Tuple[bool, Optional[str]]:
    """Poll generation status until video is ready.

    Returns (is_ready, video_url_or_error).
    """
    project_id = project_id or DEFAULT_PROJECT
    clean_id = extract_media_id(media_id) or media_id
    endpoint = ENDPOINTS["poll_status"]
    body = {
        "media": [
            {"name": clean_id}
        ]
    }
    start_time = time.time()

    while time.time() - start_time < timeout:
        result = await bridge.api_request(endpoint, body, captcha_action="", method="POST")
        data = result.get("data", {}) if isinstance(result, dict) else {}
        media_list = data.get("media", [])
        status_list = data.get("mediaGenerationStatus", [])

        if media_list:
            item = media_list[0]
            status_obj = item.get("mediaMetadata", {}).get("mediaStatus", {})
            status = status_obj.get("mediaGenerationStatus") or item.get("mediaGenerationStatus", "")

            if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                logger.info("Video %s generated successfully!", clean_id)
                video_url = (
                    item.get("video", {}).get("generatedVideo", {}).get("fifeUrl")
                    or item.get("video", {}).get("fifeUrl")
                    or item.get("video", {}).get("videoUri")
                    or item.get("videoUri")
                )
                if not video_url:
                    # Fetch from flowMedia endpoint directly using bearer token
                    media_endpoint = ENDPOINTS["get_media"].format(media_id=clean_id)
                    token = bridge._flow_key or bridge._load_persisted_flow_key()
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "x-goog-api-key": _get_flow_public_api_key(),
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Origin": "https://labs.google",
                        "Referer": "https://labs.google/fx/tools/flow",
                    }
                    def _get_fm():
                        import requests
                        r = requests.get(f"https://aisandbox-pa.googleapis.com{media_endpoint}", headers=headers, timeout=15)
                        return r.json() if r.status_code == 200 else {}
                    media_data = await asyncio.to_thread(_get_fm)
                    video_url = (
                        media_data.get("video", {}).get("generatedVideo", {}).get("fifeUrl")
                        or media_data.get("video", {}).get("fifeUrl")
                        or media_data.get("video", {}).get("videoUri")
                    )
                return True, video_url
            elif "FAILED" in status or "BLOCKED" in status:
                err_detail = status_obj.get("error", {}).get("message") or status_obj.get("failureReasons") or item.get("errorMessage") or status
                logger.error("Video generation failed: %s (detail: %s)", status, err_detail)
                return False, f"{status}: {err_detail}" if err_detail != status else status

        elif status_list:
            item = status_list[0]
            status = item.get("mediaGenerationStatus", "")

            if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                logger.info("Video %s generated successfully!", clean_id)
                media_endpoint = ENDPOINTS["get_media"].format(media_id=clean_id)
                media_res = await bridge.api_request(media_endpoint, {}, captcha_action="", method="GET")
                media_data = media_res.get("data", {}) if isinstance(media_res, dict) else {}
                video_url = (
                    media_data.get("video", {}).get("videoUri")
                    or media_data.get("video", {}).get("fifeUrl")
                    or media_data.get("videoUri")
                    or media_data.get("downloadUrl")
                )
                return True, video_url
            elif "FAILED" in status or "BLOCKED" in status:
                err_detail = item.get("errorMessage") or item.get("statusDetail") or status
                logger.error("Video generation failed: %s (detail: %s)", status, err_detail)
                return False, f"{status}: {err_detail}" if err_detail != status else status

        await asyncio.sleep(poll_interval)

    return False, "TIMEOUT"


async def download_file(url: str, output_path: Path) -> Path:
    """Download a file directly from a URL to destination path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _dl():
        import requests
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        r.raise_for_status()
        output_path.write_bytes(r.content)
        return output_path

    return await asyncio.to_thread(_dl)
