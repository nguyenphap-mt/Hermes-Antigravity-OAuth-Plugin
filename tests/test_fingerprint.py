import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
for _p in [_HERMES_DIR, _PLUGIN_DIR]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from bridge.fingerprint import AntigravityFingerprint
    from bridge.client import build_code_assist_request
except ImportError:
    from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
    from tools.antigravity_bridge.client import build_code_assist_request


class TestAntigravityFingerprint(unittest.TestCase):
    """Test suite for AntigravityFingerprint dual-mode simulation."""

    def setUp(self) -> None:
        # Reset cache before each test
        AntigravityFingerprint._cached_version = None
        AntigravityFingerprint._cached_source = None
        AntigravityFingerprint._cached_binary_path = None
        AntigravityFingerprint._cached_changelist = None
        AntigravityFingerprint._cached_ls_path = None
        AntigravityFingerprint._session_trajectory_id = None

    def tearDown(self) -> None:
        AntigravityFingerprint._cached_version = None
        AntigravityFingerprint._cached_source = None
        AntigravityFingerprint._cached_binary_path = None
        AntigravityFingerprint._cached_changelist = None
        AntigravityFingerprint._cached_ls_path = None
        AntigravityFingerprint._session_trajectory_id = None

    def test_autonomous_synthetic_profile_fallback(self) -> None:
        """Verify autonomous synthetic profile triggers when no local binary is present."""
        with patch.object(AntigravityFingerprint, "_find_antigravity_binary", return_value=None):
            version, source, bin_path = AntigravityFingerprint.get_version_info(force_refresh=True)
            self.assertEqual(version, AntigravityFingerprint.DEFAULT_VERSION)
            self.assertEqual(source, "builtin_golden")
            self.assertIsNone(bin_path)

            summary = AntigravityFingerprint.get_status_summary()
            self.assertFalse(summary["is_local_binary"])
            self.assertIn("Autonomous Built-in Profile", summary["description"])

    def test_local_binary_detection_mocked(self) -> None:
        """Verify dynamic probe uses local binary when present."""
        fake_binary = Path("/fake/path/Antigravity.exe")
        with patch.object(AntigravityFingerprint, "_find_antigravity_binary", return_value=fake_binary), \
             patch.object(AntigravityFingerprint, "_read_binary_version", return_value="2.11.0"):
            version, source, bin_path = AntigravityFingerprint.get_version_info(force_refresh=True)
            self.assertEqual(version, "2.11.0")
            self.assertEqual(source, "local_binary")
            self.assertEqual(bin_path, str(fake_binary))

            summary = AntigravityFingerprint.get_status_summary()
            self.assertTrue(summary["is_local_binary"])
            self.assertIn("Synced with Local IDE", summary["description"])

    def test_build_headers_structure_and_values(self) -> None:
        """Verify generated headers contain exact Antigravity language_server.exe signatures."""
        headers = AntigravityFingerprint.build_headers("mock_token_xyz", project_id="proj-123")

        # Required headers
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer mock_token_xyz")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Accept-Encoding"], "gzip")
        self.assertNotIn("X-Goog-User-Project", headers)

        # User-Agent validation (authentic language_server.exe format)
        ua = headers["User-Agent"]
        self.assertTrue(ua.startswith("antigravity/"))
        self.assertIn("aidev_client;", ua)
        self.assertIn("os_type=", ua)
        self.assertIn("arch=", ua)
        self.assertIn("cl=", ua)

        # X-Goog-Api-Client validation (Go language_server.exe signature)
        api_client = headers["X-Goog-Api-Client"]
        self.assertIn("gl-go/1.24.0", api_client)
        self.assertIn("gccl/", api_client)
        self.assertIn("antigravity/", api_client)

        # Client-Metadata validation
        self.assertIn("Client-Metadata", headers)
        cm = json.loads(headers["Client-Metadata"])
        self.assertEqual(cm["ideType"], "ANTIGRAVITY")
        self.assertEqual(cm["pluginType"], "GEMINI")
        self.assertIn("platform", cm)
        self.assertIn("applicationVersion", cm)

        # UUID tracing validation
        self.assertIn("x-activity-request-id", headers)
        self.assertEqual(len(headers["x-activity-request-id"]), 36)
        self.assertIn("X-Aicode-Request-Id", headers)
        self.assertEqual(headers["X-Aicode-Request-Id"], headers["x-activity-request-id"])
        self.assertIn("X-Aicode-Prompt-Id", headers)
        self.assertEqual(len(headers["X-Aicode-Prompt-Id"]), 36)
        self.assertIn("X-Aicode-Trajectory-Id", headers)
        self.assertEqual(len(headers["X-Aicode-Trajectory-Id"]), 36)

    def test_platform_info_os_mapping(self) -> None:
        """Test platform info mapping for Windows, Darwin, and Linux."""
        with patch("sys.platform", "win32"):
            ua, plat = AntigravityFingerprint.get_platform_info()
            self.assertIn("Windows NT", ua)
            self.assertEqual(plat, "PLATFORM_WINDOWS")

        with patch("sys.platform", "darwin"):
            ua, plat = AntigravityFingerprint.get_platform_info()
            self.assertIn("Macintosh", ua)
            self.assertEqual(plat, "PLATFORM_DARWIN")

        with patch("sys.platform", "linux"):
            ua, plat = AntigravityFingerprint.get_platform_info()
            self.assertIn("Linux", ua)
            self.assertEqual(plat, "PLATFORM_LINUX")

    def test_changelist_detection_and_fallback(self) -> None:
        """Verify changelist detection falls back cleanly or reads from language_server."""
        with patch.object(AntigravityFingerprint, "_find_language_server_binary", return_value=None):
            cl = AntigravityFingerprint.get_changelist(force_refresh=True)
            self.assertEqual(cl, AntigravityFingerprint.DEFAULT_CHANGELIST)

        fake_ls = Path("/fake/path/language_server.exe")
        with patch.object(AntigravityFingerprint, "_find_language_server_binary", return_value=fake_ls), \
             patch.object(AntigravityFingerprint, "_read_binary_changelist", return_value="998881661"):
            cl = AntigravityFingerprint.get_changelist(force_refresh=True)
            self.assertEqual(cl, "998881661")

    def test_code_assist_request_envelope_matches_wire_format(self) -> None:
        """Verify build_code_assist_request builds the exact language_server.exe outer/inner envelope."""
        openai_payload = {
            "model": "gemini-3.8-pro-high",
            "messages": [
                {"role": "system", "content": "You are a helpful coding assistant."},
                {"role": "user", "content": "Explain this function."},
            ],
        }
        envelope = build_code_assist_request(
            openai_payload,
            project_id="useful-Frame-3bw82",
            prompt_id="prompt-uuid-1234",
            trajectory_id="traj-uuid-5678",
        )
        self.assertEqual(envelope["project"], "useful-Frame-3bw82")
        self.assertEqual(envelope["model"], "gemini-3.8-pro-high")
        self.assertEqual(envelope["userAgent"], "antigravity")
        self.assertEqual(envelope["requestType"], "agent")
        self.assertEqual(envelope["userPromptId"], "prompt-uuid-1234")
        self.assertTrue(envelope["requestId"].startswith("agent/traj-uuid-5678/"))

        inner = envelope["request"]
        self.assertEqual(inner["sessionId"], "traj-uuid-5678")
        self.assertEqual(inner["systemInstruction"], {"parts": [{"text": "You are a helpful coding assistant."}]})
        self.assertNotIn("role", inner["systemInstruction"])
        self.assertEqual(
            inner["generationConfig"]["thinkingConfig"],
            {"includeThoughts": True, "thinkingBudget": 16384},
        )


if __name__ == "__main__":
    unittest.main()
