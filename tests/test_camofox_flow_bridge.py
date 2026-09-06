"""Unit tests for CamofoxFlowBridge and Google Flow Generators."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
    from tools.antigravity_bridge.flow import generators
    from tools.antigravity_bridge.flow.automation import GoogleFlowClient, FlowResult
    from tools.antigravity_bridge.flow.tools import (
        google_flow_image,
        google_flow_video,
        google_flow_upsample,
        google_flow_status,
    )
    _TOOLS_MOD = "tools.antigravity_bridge.flow.tools"
except ImportError:
    from bridge.flow.camofox_bridge import CamofoxFlowBridge
    from bridge.flow import generators
    from bridge.flow.automation import GoogleFlowClient, FlowResult
    from bridge.flow.tools import (
        google_flow_image,
        google_flow_video,
        google_flow_upsample,
        google_flow_status,
    )
    _TOOLS_MOD = "bridge.flow.tools"


class TestCamofoxFlowBridge:
    """Test CamofoxFlowBridge lifecycle, eval, and request routing."""

    def test_is_server_running(self):
        bridge = CamofoxFlowBridge("http://127.0.0.1:9377")
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            assert bridge.is_server_running() is True

            mock_get.side_effect = Exception("offline")
            assert bridge.is_server_running() is False

    def test_ensure_tab(self):
        async def _test():
            CamofoxFlowBridge._active_tab_id = None
            bridge = CamofoxFlowBridge("http://127.0.0.1:9377")
            bridge.is_server_running = MagicMock(return_value=True)

            with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {"tabs": []}
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"tabId": "tab-123"}

                tab_id = await bridge.ensure_tab()
                assert tab_id == "tab-123"
                assert bridge.tab_id == "tab-123"
        asyncio.run(_test())

    def test_api_request_injects_recaptcha(self):
        async def _test():
            bridge = CamofoxFlowBridge("http://127.0.0.1:9377")
            bridge.ensure_tab = AsyncMock(return_value="tab-123")
            bridge.get_recaptcha_token = AsyncMock(return_value="test_captcha_token")

            # Mock evaluate to return success
            bridge.evaluate = AsyncMock(return_value=json.dumps({"status": 200, "data": {"ok": True}}))

            body = {"clientContext": {"recaptchaContext": {}}}
            res = await bridge.api_request("/v1/test", body, captcha_action="TEST_ACTION")

            assert res["status"] == 200
            assert body["clientContext"]["recaptchaContext"]["token"] == "test_captcha_token"
        asyncio.run(_test())


class TestGenerators:
    """Test Flow generator functions and payload structures."""

    def test_generate_image_payload(self):
        async def _test():
            bridge = AsyncMock()
            bridge.api_request.return_value = {
                "status": 200,
                "data": {
                    "media": [
                        {
                            "name": "11111111-2222-3333-4444-555555555555",
                            "image": {
                                "generatedImage": {
                                    "fifeUrl": "https://google.com/image.png"
                                }
                            }
                        }
                    ]
                }
            }

            results = await generators.generate_image(
                bridge,
                prompt="cyberpunk city",
                aspect="16:9",
                model="gem_pix_2",
                count=1,
            )

            assert len(results) == 1
            assert results[0]["media_id"] == "11111111-2222-3333-4444-555555555555"
            assert results[0]["image_url"] == "https://google.com/image.png"

            # Check call arguments
            call_args = bridge.api_request.call_args
            endpoint, body = call_args[0][0], call_args[0][1]
            assert "batchGenerateImages" in endpoint
            assert body["requests"][0]["imageModelName"] == "GEM_PIX_2"
            assert body["requests"][0]["imageAspectRatio"] == "IMAGE_ASPECT_RATIO_LANDSCAPE"
        asyncio.run(_test())

    def test_generate_video_payload(self):
        async def _test():
            bridge = AsyncMock()
            bridge.api_request.return_value = {
                "status": 200,
                "data": {
                    "media": [{"name": "vid-1234"}]
                }
            }

            media_ids = await generators.generate_video(
                bridge,
                prompt="drone shot of mountains",
                aspect="landscape",
                duration=6,
            )

            assert media_ids == ["vid-1234"]
            call_args = bridge.api_request.call_args
            body = call_args[0][1]
            assert body["requests"][0]["videoModelKey"] == "abra_t2v_6s"
        asyncio.run(_test())

    def test_upsample_video_payload(self):
        async def _test():
            bridge = AsyncMock()
            bridge.api_request.return_value = {
                "status": 200,
                "data": {
                    "media": [{"name": "vid-4k-upsampled"}]
                }
            }

            media_ids = await generators.upsample_video(
                bridge,
                media_id="source-vid-123",
                resolution="4k",
            )

            assert media_ids == ["vid-4k-upsampled"]
            call_args = bridge.api_request.call_args
            body = call_args[0][1]
            assert body["requests"][0]["videoModelKey"] == "veo_3_1_upsampler_4k"
            assert body["requests"][0]["resolution"] == "VIDEO_RESOLUTION_4K"
            assert body["requests"][0]["videoInput"]["mediaId"] == "source-vid-123"
        asyncio.run(_test())

    def test_poll_video_status(self):
        async def _test():
            bridge = AsyncMock()
            # 1st call pending, 2nd call success, 3rd call get_media
            bridge.api_request.side_effect = [
                {"status": 200, "data": {"mediaGenerationStatus": [{"mediaGenerationStatus": "PENDING"}]}},
                {"status": 200, "data": {"mediaGenerationStatus": [{"mediaGenerationStatus": "MEDIA_GENERATION_STATUS_SUCCESSFUL"}]}},
                {"status": 200, "data": {"video": {"videoUri": "https://google.com/final_video.mp4"}}},
            ]

            ready, url = await generators.poll_video_status(bridge, "vid-123", timeout=10, poll_interval=0.01)
            assert ready is True
            assert url == "https://google.com/final_video.mp4"
        asyncio.run(_test())


class TestGoogleFlowTools:
    """Test public sync tool wrappers."""

    def test_upsample_tool_wrapper(self):
        with patch(f"{_TOOLS_MOD}._get_or_create_client") as mock_client:
            mock_inst = AsyncMock()
            mock_inst.upsample_video.return_value = FlowResult(
                success=True,
                file_path="/tmp/upsampled.mp4",
                media_type="video",
                media_id="new-media-id",
                duration_seconds=5.0,
            )
            mock_client.return_value = mock_inst

            res = google_flow_upsample("old-id", resolution="1080p")
            assert res["success"] is True
            assert res["file_path"] == "/tmp/upsampled.mp4"
            assert "✅" in res["message"]

    def test_status_tool_wrapper(self):
        with patch(f"{_TOOLS_MOD}._get_or_create_client") as mock_client:
            mock_inst = AsyncMock()
            mock_inst.check_status.return_value = {
                "server_running": True,
                "tab_connected": True,
                "logged_in": True,
            }
            mock_client.return_value = mock_inst

            status = google_flow_status()
            assert status["server_running"] is True
            assert status["logged_in"] is True
