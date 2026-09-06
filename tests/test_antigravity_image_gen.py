import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

plugin_root = Path(__file__).resolve().parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
hermes_root = plugin_root.parent / "hermes-agent"
if hermes_root.exists() and str(hermes_root) not in sys.path:
    sys.path.insert(0, str(hermes_root))

try:
    from plugins.image_gen.antigravity import (
        AntigravityImageGenProvider,
        _load_image_as_b64,
        _ASPECT_RATIO_DESCRIPTIONS,
    )
except ImportError:
    from image_gen.antigravity import (
        AntigravityImageGenProvider,
        _load_image_as_b64,
        _ASPECT_RATIO_DESCRIPTIONS,
    )


class TestAntigravityImageGenProvider(unittest.TestCase):
    def setUp(self):
        self.provider = AntigravityImageGenProvider()

    def test_provider_metadata_and_capabilities(self):
        self.assertEqual(self.provider.name, "antigravity")
        cfg = self.provider.get_config()
        self.assertIn("gemini 3.1 flash image", cfg["display_name"].lower())
        caps = self.provider.capabilities()
        self.assertEqual(caps["modalities"], ["text", "image"])
        self.assertGreaterEqual(caps["max_reference_images"], 1)

    def test_aspect_ratio_mappings(self):
        for ar in ["1:1", "16:9", "9:16", "4:3", "3:4"]:
            self.assertIn(ar, _ASPECT_RATIO_DESCRIPTIONS)

    def test_load_image_as_b64_local_file(self):
        # Create a small temp file
        temp_img = Path("test_temp_img.jpg")
        temp_img.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")
        try:
            res = _load_image_as_b64(str(temp_img))
            self.assertIsNotNone(res)
            mime, b64_data = res
            self.assertEqual(mime, "image/jpeg")
            self.assertTrue(len(b64_data) > 0)
        finally:
            if temp_img.exists():
                temp_img.unlink()

    def test_generate_requires_non_empty_prompt(self):
        res = self.provider.generate("")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("error_type"), "invalid_argument")

    def test_generate_success_mock(self):
        mock_c = MagicMock()
        mock_c.access_token = "mock_token"
        mock_c.project_id = "test-project"

        mock_resp_data = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/jpeg",
                                        "data": "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=",
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        auth_targets = [
            "tools.antigravity_bridge.auth.AntigravityAuthManager.resolve_valid_credentials",
            "bridge.auth.AntigravityAuthManager.resolve_valid_credentials",
        ]

        def _run_with_patches(idx=0):
            if idx >= len(auth_targets):
                return self.provider.generate("A friendly cat sitting on a rug", aspect_ratio="1:1")
            target = auth_targets[idx]
            try:
                with patch(target, return_value=mock_c):
                    return _run_with_patches(idx + 1)
            except (ImportError, AttributeError):
                return _run_with_patches(idx + 1)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = _run_with_patches()
            self.assertTrue(res.get("success"), f"Generation failed: {res.get('error')}")
            self.assertEqual(res.get("model"), "gemini-3.1-flash-image")
            self.assertEqual(res.get("provider"), "antigravity")
            img_path = res.get("image")
            self.assertTrue(os.path.exists(img_path))
            if os.path.exists(img_path):
                os.remove(img_path)


if __name__ == "__main__":
    unittest.main()
