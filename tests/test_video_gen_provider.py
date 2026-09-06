"""Automated tests for Antigravity Video Generation Provider (Google Flow / Veo)."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from video_gen.antigravity import AntigravityVideoGenProvider, VEO_MODELS


def test_video_gen_provider_metadata():
    """Verify provider name, display name, and model list."""
    provider = AntigravityVideoGenProvider()
    assert provider.name == "antigravity"
    assert "Google Flow" in provider.display_name
    assert provider.default_model() == "omni-1.1-flash"

    models = provider.list_models()
    assert len(models) >= 5
    model_ids = [m["id"] for m in models]
    assert "omni-1.1-flash" in model_ids
    assert "veo-3.1-lite" in model_ids
    assert "veo-3.1-fast" in model_ids
    assert "veo-2-10s" in model_ids
    assert "veo-i2v" in model_ids


def test_video_gen_provider_capabilities():
    """Verify provider capabilities match Google Flow specs."""
    provider = AntigravityVideoGenProvider()
    caps = provider.capabilities()
    assert "text" in caps["modalities"]
    assert "image" in caps["modalities"]
    assert "16:9" in caps["aspect_ratios"]
    assert "9:16" in caps["aspect_ratios"]
    assert caps["max_duration"] == 10
    assert caps["min_duration"] == 4


def test_resolve_duration_smart_mapping():
    """Verify prompt-aware duration resolution."""
    provider = AntigravityVideoGenProvider()

    # Explicit duration overrides
    assert provider._resolve_duration("bất kỳ", duration=6, model=None) == 6
    assert provider._resolve_duration("bất kỳ", duration=4, model=None) == 4

    # Model name overrides
    assert provider._resolve_duration("bất kỳ", duration=None, model="veo-2-6s") == 6
    assert provider._resolve_duration("bất kỳ", duration=None, model="preview") == 4

    # Prompt keywords
    assert provider._resolve_duration("Tạo video nhanh một chú mèo", duration=None, model=None) == 6
    assert provider._resolve_duration("Tạo video 6s về chiếc xe", duration=None, model=None) == 6
    assert provider._resolve_duration("Tạo bản preview 4s", duration=None, model=None) == 4
    assert provider._resolve_duration("Tạo video 8 giây", duration=None, model=None) == 8
    assert provider._resolve_duration("Tạo video chất lượng điện ảnh 10s", duration=None, model=None) == 10

    # Default
    assert provider._resolve_duration("Một chú chó đang chạy", duration=None, model=None) == 10


def test_generate_video_success_mock(tmp_path):
    """Test full generate() flow with mocked Google Flow bridge."""
    provider = AntigravityVideoGenProvider()

    mock_mp4 = tmp_path / "mock_video.mp4"
    mock_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"A" * 2000)

    with patch("bridge.flow.flow_refresh_daemon.FlowRefreshDaemon.ensure_active_token", new_callable=AsyncMock) as mock_token, \
         patch("bridge.flow.generators.generate_video", new_callable=AsyncMock) as mock_gen, \
         patch("bridge.flow.generators.poll_video_status", new_callable=AsyncMock) as mock_poll, \
         patch("bridge.flow.generators.download_file", new_callable=AsyncMock) as mock_dl:

        mock_token.return_value = (True, "ya29.mock_token")
        mock_gen.return_value = ["mock-media-uuid-1234"]
        mock_poll.return_value = (True, "https://storage.googleapis.com/test.mp4")

        def _fake_dl(url, path):
            Path(path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"A" * 2000)
            return path
        mock_dl.side_effect = _fake_dl

        # Redirect home media directory to tmp_path
        with patch("video_gen.antigravity._h_home", tmp_path):
            resp = provider.generate("Một chú chó chạy trên bãi cỏ", duration=6, aspect_ratio="16:9")

            assert resp["success"] is True
            assert resp["provider"] == "antigravity"
            assert resp["duration"] == 6
            assert resp["aspect_ratio"] == "16:9"
            assert resp["model"] == "veo-3.1-lite"
            assert resp["prompt"] == "Một chú chó chạy trên bãi cỏ"


def test_register_plugin():
    """Verify register(ctx) passes instance to ctx.register_video_gen_provider."""
    from video_gen.antigravity import register
    mock_ctx = MagicMock()
    register(mock_ctx)
    assert mock_ctx.register_video_gen_provider.call_count == 1
    passed_provider = mock_ctx.register_video_gen_provider.call_args[0][0]
    assert isinstance(passed_provider, AntigravityVideoGenProvider)
