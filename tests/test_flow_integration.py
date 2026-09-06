"""Tests for Google Flow integration module."""

import asyncio
import pytest
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

try:
    from tools.antigravity_bridge.flow.automation import (
        FlowResult,
        GoogleFlowClient,
        DEFAULT_TIMEOUT_SECONDS,
        DEFAULT_MEDIA_DIR,
    )
    from tools.antigravity_bridge.flow import selectors
    from tools.antigravity_bridge.flow.cookie_bridge import (
        verify_login,
        extract_session_cookies,
        restore_session_cookies,
    )
except ImportError:
    from bridge.flow.automation import (
        FlowResult,
        GoogleFlowClient,
        DEFAULT_TIMEOUT_SECONDS,
        DEFAULT_MEDIA_DIR,
    )
    from bridge.flow import selectors
    from bridge.flow.cookie_bridge import (
        verify_login,
        extract_session_cookies,
        restore_session_cookies,
    )


# =============================================================================
# FlowResult Tests
# =============================================================================


class TestFlowResult:
    """Tests for FlowResult dataclass."""

    def test_default_values(self):
        result = FlowResult(success=False)
        assert result.success is False
        assert result.file_path is None
        assert result.flow_url is None
        assert result.media_type == "unknown"
        assert result.prompt == ""
        assert result.duration_seconds == 0.0
        assert result.error is None
        assert result.metadata == {}

    def test_success_result(self):
        result = FlowResult(
            success=True,
            file_path="/tmp/test.mp4",
            flow_url="https://labs.google/fx/creation/123",
            media_type="video",
            prompt="a cat dancing",
            duration_seconds=45.3,
        )
        assert result.success is True
        assert result.file_path == "/tmp/test.mp4"
        assert result.media_type == "video"

    def test_to_dict(self):
        result = FlowResult(
            success=True,
            file_path="/tmp/test.png",
            media_type="image",
            prompt="sunset",
            duration_seconds=12.789,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["file_path"] == "/tmp/test.png"
        assert d["media_type"] == "image"
        assert d["duration_seconds"] == 12.8  # rounded

    def test_error_result(self):
        result = FlowResult(
            success=False,
            media_type="video",
            prompt="test",
            error="Timed out after 600s",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Timed out after 600s"


# =============================================================================
# Selectors Tests
# =============================================================================


class TestSelectors:
    """Tests for Google Flow UI selectors."""

    def test_flow_base_url(self):
        assert "labs.google" in selectors.FLOW_BASE_URL
        assert "/fx/tools/flow" in selectors.FLOW_BASE_URL

    def test_flow_editor_url(self):
        assert "create" in selectors.FLOW_EDITOR_URL

    def test_prompt_input_selector(self):
        assert "textarea" in selectors.PROMPT_INPUT

    def test_generate_button_selector(self):
        assert "Generate" in selectors.GENERATE_BTN

    def test_video_result_selector(self):
        assert "video" in selectors.VIDEO_RESULT

    def test_image_result_selector(self):
        assert "img" in selectors.IMAGE_RESULT

    def test_audio_result_selector(self):
        assert "audio" in selectors.AUDIO_RESULT

    def test_download_button_selector(self):
        assert "ownload" in selectors.DOWNLOAD_BTN

    def test_loading_indicator_selector(self):
        assert "progressbar" in selectors.LOADING_INDICATOR

    def test_tool_buttons_exist(self):
        assert "Video" in selectors.VIDEO_TOOL_BTN
        assert "Image" in selectors.IMAGE_TOOL_BTN
        assert "Music" in selectors.MUSIC_TOOL_BTN


# =============================================================================
# CookieBridge Tests
# =============================================================================


class TestCookieBridge:
    """Tests for OAuth token to browser cookie bridge."""

    def test_verify_login_with_avatar(self):
        async def _test():
            page = AsyncMock()
            page.query_selector = AsyncMock(return_value=MagicMock())
            return await verify_login(page)
        assert asyncio.run(_test()) is True

    def test_verify_login_with_sign_in_button(self):
        async def _test():
            page = AsyncMock()
            page.query_selector = AsyncMock(side_effect=[None, MagicMock()])
            return await verify_login(page)
        assert asyncio.run(_test()) is False

    def test_verify_login_on_accounts_page(self):
        async def _test():
            page = AsyncMock()
            page.query_selector = AsyncMock(return_value=None)
            type(page).url = PropertyMock(return_value="https://accounts.google.com/signin")
            return await verify_login(page)
        assert asyncio.run(_test()) is False

    def test_verify_login_on_flow_page(self):
        async def _test():
            page = AsyncMock()
            page.query_selector = AsyncMock(return_value=None)
            type(page).url = PropertyMock(return_value="https://labs.google/fx/tools/flow")
            return await verify_login(page)
        assert asyncio.run(_test()) is True

    def test_extract_session_cookies(self):
        async def _test():
            context = AsyncMock()
            context.cookies = AsyncMock(return_value=[
                {"name": "SID", "domain": ".google.com", "value": "abc"},
                {"name": "NID", "domain": ".google.com", "value": "def"},
                {"name": "unrelated", "domain": ".example.com", "value": "xyz"},
            ])
            return await extract_session_cookies(context)
        cookies = asyncio.run(_test())
        assert len(cookies) == 2
        assert all(
            any(d in c["domain"] for d in [".google.com", ".labs.google"])
            for c in cookies
        )

    def test_restore_session_cookies(self):
        async def _test():
            context = AsyncMock()
            test_cookies = [{"name": "SID", "domain": ".google.com", "value": "test"}]
            await restore_session_cookies(context, test_cookies)
            context.add_cookies.assert_called_once_with(test_cookies)
        asyncio.run(_test())


# =============================================================================
# GoogleFlowClient Tests
# =============================================================================


class TestGoogleFlowClient:
    """Tests for the main Google Flow automation client."""

    def test_default_config(self):
        client = GoogleFlowClient()
        assert client.headless is True
        assert client.timeout == DEFAULT_TIMEOUT_SECONDS
        assert client.media_dir == DEFAULT_MEDIA_DIR
        assert client.access_token == ""
        assert client._is_logged_in is False

    def test_custom_config(self):
        from pathlib import Path
        client = GoogleFlowClient(
            access_token="ya29.test",
            email="test@gmail.com",
            headless=False,
            timeout=300,
            media_dir=Path("/tmp/flow"),
        )
        assert client.access_token == "ya29.test"
        assert client.email == "test@gmail.com"
        assert client.headless is False
        assert client.timeout == 300

    def test_media_dir_default(self):
        from pathlib import Path
        assert DEFAULT_MEDIA_DIR == Path.home() / ".hermes" / "media" / "flow"

    def test_timeout_default(self):
        assert DEFAULT_TIMEOUT_SECONDS == 600  # 10 minutes


# =============================================================================
# Tools Tests (sync wrappers)
# =============================================================================


class TestToolFunctions:
    """Tests for Hermes tool registration functions."""

    def test_format_result_success(self):
        from tools.antigravity_bridge.flow.tools import _format_result
        result = FlowResult(
            success=True,
            file_path="/tmp/test.mp4",
            flow_url="https://labs.google/fx/creation/123",
            media_type="video",
            prompt="test",
            duration_seconds=45.0,
        )
        formatted = _format_result(result)
        assert formatted["success"] is True
        assert "✅" in formatted["message"]
        assert "/tmp/test.mp4" in formatted["message"]
        assert "45.0s" in formatted["message"]

    def test_format_result_failure(self):
        from tools.antigravity_bridge.flow.tools import _format_result
        result = FlowResult(
            success=False,
            media_type="video",
            prompt="test",
            error="Timed out",
        )
        formatted = _format_result(result)
        assert formatted["success"] is False
        assert "❌" in formatted["message"]
        assert "Timed out" in formatted["message"]
