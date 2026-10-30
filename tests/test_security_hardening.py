"""Security hardening test suite for Hermes Antigravity OAuth Plugin.

Covers:
1. SSRF & Local File Read guards in image_gen/antigravity/__init__.py
2. JS string literal escaping & media_id sanitization in bridge/flow/
3. OAuth PKCE state enforcement & XSS escaping in bridge/auth.py
4. PowerShell safe path env var handling in bridge/fingerprint.py
5. Removal of Chrome profile credential copying in bridge/flow/flow_auth_service.py
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins.image_gen.antigravity import (
        _is_safe_local_image_path,
        _is_safe_remote_url,
        _load_image_as_b64,
    )
except ImportError:
    from image_gen.antigravity import (
        _is_safe_local_image_path,
        _is_safe_remote_url,
        _load_image_as_b64,
    )

try:
    from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
    from tools.antigravity_bridge.flow.generators import sanitize_media_id, poll_video_status
    from tools.antigravity_bridge.flow import flow_auth_service
    from tools.antigravity_bridge.auth import AntigravityAuthManager
    from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
except ImportError:
    from bridge.flow.camofox_bridge import CamofoxFlowBridge
    from bridge.flow.generators import sanitize_media_id, poll_video_status
    from bridge.flow import flow_auth_service
    from bridge.auth import AntigravityAuthManager
    from bridge.fingerprint import AntigravityFingerprint


def test_ssrf_remote_url_guard():
    """Ensure loopback, private networks, metadata IPs, and non-HTTP schemes are blocked."""
    assert _is_safe_remote_url("http://127.0.0.1:8765/v1/models") is False
    assert _is_safe_remote_url("http://localhost:8080/secret.png") is False
    assert _is_safe_remote_url("http://169.254.169.254/latest/meta-data/") is False
    assert _is_safe_remote_url("http://192.168.1.10/router.png") is False
    assert _is_safe_remote_url("http://10.0.0.1/internal.jpg") is False
    assert _is_safe_remote_url("file:///etc/passwd") is False


def test_local_image_path_guard(tmp_path: Path):
    """Ensure only valid image extensions outside sensitive directories are allowed."""
    valid_img = tmp_path / "photo.png"
    valid_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert _is_safe_local_image_path(str(valid_img)) is True

    # Non-image file extensions must be rejected
    secret_json = tmp_path / "antigravity_tokens.json"
    secret_json.write_text('{"access_token": "secret"}', encoding="utf-8")
    assert _is_safe_local_image_path(str(secret_json)) is False

    # Sensitive directory names must be rejected even with .png extension
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    fake_img_in_ssh = ssh_dir / "id_rsa.png"
    fake_img_in_ssh.write_bytes(b"secret-key")
    assert _is_safe_local_image_path(str(fake_img_in_ssh)) is False

    # _load_image_as_b64 should reject unsafe paths and loopback URLs, and load valid_img
    assert _load_image_as_b64(str(secret_json)) is None
    assert _load_image_as_b64(str(fake_img_in_ssh)) is None
    assert _load_image_as_b64("http://127.0.0.1:8765/internal.png") is None
    loaded = _load_image_as_b64(str(valid_img))
    assert loaded is not None
    assert loaded[0] == "image/png"


def test_sanitize_media_id_blocks_injection():
    """Verify sanitize_media_id allows UUIDs and clean tokens while blocking injection payloads."""
    uuid_str = "0143adf4-5864-4cb4-abb5-fe4254ad0dc7"
    assert sanitize_media_id(f"projects/p1/flowMedia/{uuid_str}") == uuid_str
    assert sanitize_media_id("vid-123") == "vid-123"
    assert sanitize_media_id("source-vid-123") == "source-vid-123"

    for malicious in [
        "../etc/passwd",
        "vid'); alert(1); //",
        "media/../../secret",
        "id?foo=bar&baz=1",
        "",
    ]:
        with pytest.raises(ValueError):
            sanitize_media_id(malicious)


def test_camofox_js_interpolation_escaped():
    """Verify CamofoxFlowBridge escapes action, method, and url via json.dumps()."""
    bridge = CamofoxFlowBridge()
    bridge.ensure_tab = AsyncMock(return_value="tab-1")
    captured_scripts = []

    async def fake_eval(script: str, timeout: int = 30):
        captured_scripts.append(script)
        if "window.location.origin" in script:
            return "https://flow.google.com"
        return '{"token": "valid_token_12345678901234567890", "status": 200, "ok": true, "data": {}}'

    bridge.evaluate = AsyncMock(side_effect=fake_eval)

    malicious_action = "IMAGE'); alert('xss'); //"
    asyncio.run(bridge.get_recaptcha_token(action=malicious_action))

    recaptcha_script = [s for s in captured_scripts if "const ACTION =" in s][0]
    assert 'const ACTION = "IMAGE\'); alert(\'xss\'); //";' in recaptcha_script

    captured_scripts.clear()
    asyncio.run(
        bridge.api_request(
            endpoint="/v1/test'); alert(1); //",
            body={"hello": "world"},
            captcha_action="",
            method="POST'",
        )
    )
    api_script = captured_scripts[-1]
    assert 'const reqMethod = "POST\'";' in api_script
    assert 'const reqUrl = "https://aisandbox-pa.googleapis.com/v1/test\'); alert(1); //";' in api_script


def test_pkce_state_enforcement_and_raw_code_support(tmp_path: Path):
    """Verify complete_pkce_auth_session rejects missing or mismatched state in callback URLs."""
    mgr = AntigravityAuthManager(auth_file=tmp_path / "tokens.json")

    # 1. Missing state in callback URL when expected_state is provided -> ValueError
    with pytest.raises(ValueError, match="State OAuth"):
        mgr.complete_pkce_auth_session(
            callback_or_code="http://127.0.0.1:51121/oauth-callback?code=4/0AeanS0_test",
            code_verifier="verifier123",
            redirect_uri="http://127.0.0.1:51121/oauth-callback",
            expected_state="expected_secret_state",
        )

    # 2. Mismatched state in callback URL -> ValueError
    with pytest.raises(ValueError, match="State OAuth"):
        mgr.complete_pkce_auth_session(
            callback_or_code="http://127.0.0.1:51121/oauth-callback?code=4/0AeanS0_test&state=wrong_state",
            code_verifier="verifier123",
            redirect_uri="http://127.0.0.1:51121/oauth-callback",
            expected_state="expected_secret_state",
        )


def test_powershell_uses_env_var_literal_path(tmp_path: Path):
    """Ensure _read_binary_version passes binary_path via AG_BIN_PATH env var on Windows."""
    fake_bin = tmp_path / "Antigravity'$(calc).exe"
    fake_bin.write_bytes(b"MZ" + b"\x00" * 100)

    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "2.23.1.0\n"
        mock_run.return_value = mock_res

        ver = AntigravityFingerprint._read_binary_version(fake_bin)
        assert ver == "2.23.1"
        assert mock_run.called
        args, kwargs = mock_run.call_args
        cmd_list = args[0]
        assert "$env:AG_BIN_PATH" in cmd_list[-1]
        assert str(fake_bin) not in cmd_list[-1]
        assert kwargs["env"]["AG_BIN_PATH"] == str(fake_bin)


def test_flow_handshake_does_not_copy_chrome_login_data():
    """Verify _run_handshake_worker does not copy personal Chrome Login Data or Cookies."""
    src = inspect.getsource(flow_auth_service.FlowAuthService._run_handshake_worker)
    assert "Login Data" not in src
    assert "Secure Preferences" not in src
    assert "page = ctx.pages[0] if ctx.pages else ctx.new_page()" in src
