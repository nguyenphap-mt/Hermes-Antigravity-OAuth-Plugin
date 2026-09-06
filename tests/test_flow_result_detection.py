"""Automated tests for Google Flow Image & Video Result Detection and Polling."""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Ensure sys.path setup
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
if _HERMES_DIR.exists():
    if str(_HERMES_DIR) in sys.path:
        sys.path.remove(str(_HERMES_DIR))
    sys.path.insert(0, str(_HERMES_DIR))

try:
    from bridge.flow import generators
    from bridge.flow.generators import _parse_image_results, poll_video_status, download_file
except ImportError:
    from tools.antigravity_bridge.flow import generators
    from tools.antigravity_bridge.flow.generators import _parse_image_results, poll_video_status, download_file


class TestFlowResultDetection:
    """Test suite verifying result parsing and status polling for Google Flow."""

    def test_parse_image_results_standard(self):
        """Must correctly extract media_id and fifeUrl from standard Google Flow response."""
        data = {
            "media": [
                {
                    "name": "projects/test/locations/us/media/c03b8794-22d5-455b-a48f-3669c5e317c2",
                    "image": {
                        "generatedImage": {
                            "fifeUrl": "https://lh3.googleusercontent.com/fife/ABX-test1",
                            "imageUri": "https://lh3.googleusercontent.com/uri1",
                        }
                    },
                },
                {
                    "name": "projects/test/locations/us/media/b12a9876-11c4-333a-999f-123456789abc",
                    "image": {
                        "generatedImage": {
                            "imageUri": "https://lh3.googleusercontent.com/uri2",
                        }
                    },
                },
            ]
        }
        results = _parse_image_results(data)
        assert len(results) == 2
        assert results[0]["image_url"] == "https://lh3.googleusercontent.com/fife/ABX-test1"
        assert results[0]["media_id"] == "c03b8794-22d5-455b-a48f-3669c5e317c2"
        assert results[1]["image_url"] == "https://lh3.googleusercontent.com/uri2"
        assert results[1]["media_id"] == "b12a9876-11c4-333a-999f-123456789abc"

    def test_parse_image_results_fallback_uuid_from_url(self):
        """Must fallback to searching UUID from URL if name doesn't match UUID regex."""
        data = {
            "media": [
                {
                    "name": "no-uuid-here",
                    "image": {
                        "generatedImage": {
                            "fifeUrl": "https://lh3.googleusercontent.com/media/a0b1c2d3-e4f5-6789-0123-456789abcdef/view",
                        }
                    },
                }
            ]
        }
        results = _parse_image_results(data)
        assert len(results) == 1
        assert results[0]["media_id"] == "a0b1c2d3-e4f5-6789-0123-456789abcdef"

    def test_parse_image_results_empty(self):
        """Must return empty list if media is empty or malformed."""
        assert _parse_image_results({}) == []
        assert _parse_image_results({"media": []}) == []
        assert _parse_image_results({"media": [{"image": {}}]}) == []

    def test_poll_video_status_success(self):
        """Must successfully detect MEDIA_GENERATION_STATUS_SUCCESSFUL and fetch videoUri."""
        async def _run():
            bridge = MagicMock()
            media_id = "test-vid-1234"

            # Mock api_request:
            # 1st call: status check returns MEDIA_GENERATION_STATUS_SUCCESSFUL
            # 2nd call: get_media returns videoUri
            status_resp = {
                "status": 200,
                "data": {
                    "mediaGenerationStatus": [
                        {"mediaGenerationStatus": "MEDIA_GENERATION_STATUS_SUCCESSFUL"}
                    ]
                },
            }
            media_resp = {
                "status": 200,
                "data": {
                    "video": {
                        "videoUri": "https://storage.googleapis.com/test-bucket/video.mp4"
                    }
                },
            }
            bridge.api_request = AsyncMock(side_effect=[status_resp, media_resp])

            is_ready, video_url = await poll_video_status(
                bridge, media_id=media_id, timeout=10, poll_interval=0.01
            )
            assert is_ready is True
            assert video_url == "https://storage.googleapis.com/test-bucket/video.mp4"
            assert bridge.api_request.call_count == 2

        asyncio.run(_run())

    def test_poll_video_status_blocked_or_failed(self):
        """Must immediately detect FAILED or BLOCKED policy status without waiting for timeout."""
        async def _run():
            bridge = MagicMock()
            media_id = "test-vid-fail"

            failed_resp = {
                "status": 200,
                "data": {
                    "mediaGenerationStatus": [
                        {
                            "mediaGenerationStatus": "MEDIA_GENERATION_STATUS_BLOCKED_POLICY",
                            "errorMessage": "Safety threshold violated",
                        }
                    ]
                },
            }
            bridge.api_request = AsyncMock(return_value=failed_resp)

            is_ready, err = await poll_video_status(
                bridge, media_id=media_id, timeout=10, poll_interval=0.01
            )
            assert is_ready is False
            assert "BLOCKED" in err
            assert "Safety threshold violated" in err
            assert bridge.api_request.call_count == 1

        asyncio.run(_run())

    def test_poll_video_status_timeout(self):
        """Must return False, 'TIMEOUT' when generation does not finish within timeout."""
        async def _run():
            bridge = MagicMock()
            media_id = "test-vid-pending"

            pending_resp = {
                "status": 200,
                "data": {
                    "mediaGenerationStatus": [
                        {"mediaGenerationStatus": "MEDIA_GENERATION_STATUS_PENDING"}
                    ]
                },
            }
            bridge.api_request = AsyncMock(return_value=pending_resp)

            # Fast timeout of 0.05s
            is_ready, err = await poll_video_status(
                bridge, media_id=media_id, timeout=0.05, poll_interval=0.02
            )
            assert is_ready is False
            assert err == "TIMEOUT"

        asyncio.run(_run())
