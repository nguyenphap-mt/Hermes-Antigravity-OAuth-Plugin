import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_HERMES_DIR = _PLUGIN_DIR.parent / "hermes-agent"
for _p in [_PLUGIN_DIR, _HERMES_DIR]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
except ImportError:
    from bridge.fingerprint import AntigravityFingerprint


class TestAntigravityFingerprint(unittest.TestCase):
    """Test suite for AntigravityFingerprint dual-mode simulation."""

    def setUp(self) -> None:
        # Reset cache before each test
        AntigravityFingerprint._cached_version = None
        AntigravityFingerprint._cached_source = None
        AntigravityFingerprint._cached_binary_path = None

    def tearDown(self) -> None:
        AntigravityFingerprint._cached_version = None
        AntigravityFingerprint._cached_source = None
        AntigravityFingerprint._cached_binary_path = None

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
        """Verify generated headers contain exact Antigravity IDE signatures."""
        headers = AntigravityFingerprint.build_headers("mock_token_xyz", project_id="proj-123")

        # Required headers
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer mock_token_xyz")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["X-Goog-User-Project"], "proj-123")

        # aicode-consumers should NOT set X-Goog-User-Project
        headers_consumer = AntigravityFingerprint.build_headers("mock_token_xyz", project_id="aicode-consumers")
        self.assertNotIn("X-Goog-User-Project", headers_consumer)

        # User-Agent validation
        ua = headers["User-Agent"]
        self.assertTrue(ua.startswith("Antigravity/"))
        self.assertIn("Code-Assist/", ua)

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


if __name__ == "__main__":
    unittest.main()
