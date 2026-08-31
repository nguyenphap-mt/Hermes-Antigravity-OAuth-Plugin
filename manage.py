#!/usr/bin/env python3
"""CLI utility to manage the Antigravity Local OAuth Bridge for Hermes Agent.

Usage:
  python manage.py start     # Start bridge server daemon
  python manage.py stop      # Stop bridge server
  python manage.py status    # Check status and token health
  python manage.py login     # Log in via Google OAuth PKCE
  python manage.py install   # Install plugin to ~/.hermes/ for upgrade persistence
  python manage.py setup     # Configure Hermes config.yaml to use Antigravity
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PLUGIN_ROOT.parent

# Add paths to sys.path so imports work
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from bridge.auth import AntigravityAuthManager, get_hermes_dir
    from bridge.server import (
        DEFAULT_BRIDGE_HOST,
        DEFAULT_BRIDGE_PORT,
        get_log_file,
        get_pid_file,
        is_server_running,
    )
except ImportError:
    from tools.antigravity_bridge.auth import AntigravityAuthManager, get_hermes_dir
    from tools.antigravity_bridge.server import (
        DEFAULT_BRIDGE_HOST,
        DEFAULT_BRIDGE_PORT,
        get_log_file,
        get_pid_file,
        is_server_running,
    )


def cmd_start(args: argparse.Namespace) -> int:
    port = args.port or DEFAULT_BRIDGE_PORT
    host = args.host or DEFAULT_BRIDGE_HOST
    pid_file = get_pid_file()
    log_file = get_log_file()

    if is_server_running(host, port):
        print(f"[*] Antigravity Bridge is already running on http://{host}:{port}")
        return 0

    if getattr(args, "foreground", False):
        print(f"[*] Starting Antigravity Bridge in foreground on http://{host}:{port}...")
        try:
            from bridge.server import run_server
        except ImportError:
            from tools.antigravity_bridge.server import run_server
        run_server(host=host, port=port)
        return 0

    print(f"[*] Starting Antigravity Bridge daemon on http://{host}:{port}...")

    log_fd = open(log_file, "a", encoding="utf-8")

    # SECURITY: avoid Python string interpolation into -c (code injection risk).
    # Pass host/port via env vars; spawned process reads BRIDGE_HOST/BRIDGE_PORT.
    # Use `python -m antigravity_bridge.server` (not -c) so relative imports work
    # and host/port cannot be injected into Python source.
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "antigravity_bridge.server",
    ]

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["BRIDGE_HOST"] = host
    env["BRIDGE_PORT"] = str(port)

    flags = 0
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x01000000

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PLUGIN_ROOT / "tools"),
            stdout=log_fd,
            stderr=log_fd,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            env=env,
        )
    except Exception:
        flags = 0x00000008 | 0x00000200
        proc = subprocess.Popen(
            cmd,
            cwd=str(PLUGIN_ROOT / "tools"),
            stdout=log_fd,
            stderr=log_fd,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            env=env,
        )

    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    deadline = time.time() + 10.0
    while time.time() < deadline:
        if is_server_running(host, port):
            print(f"[+] Antigravity Bridge started successfully (PID: {proc.pid})")
            print(f"    Endpoint: http://{host}:{port}/v1")
            print(f"    Logs:     {log_file}")
            return 0
        time.sleep(0.3)

    print("[-] Bridge process started but healthcheck timed out. Check logs at:", log_file)
    return 1


def cmd_stop(args: argparse.Namespace) -> int:
    pid_file = get_pid_file()
    if not pid_file.is_file():
        print("[*] No active bridge PID file found.")
        return 0

    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception:
        pid = 0

    if pid > 0:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"[+] Stopped Antigravity Bridge (PID: {pid})")
        except Exception as e:
            print(f"[*] Process {pid} not running or failed to stop: {e}")

    pid_file.unlink(missing_ok=True)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    port = args.port or DEFAULT_BRIDGE_PORT
    host = args.host or DEFAULT_BRIDGE_HOST

    running = is_server_running(host, port)
    auth_mgr = AntigravityAuthManager()
    creds = auth_mgr.load_stored_credentials() or auth_mgr.discover_local_tokens()

    print("=" * 55)
    print("       ANTIGRAVITY OAUTH BRIDGE STATUS REPORT        ")
    print("=" * 55)
    print(f"  Server Running:  {'YES [ONLINE]' if running else 'NO [OFFLINE]'}")
    print(f"  Listening On:    http://{host}:{port}/v1")
    print(f"  PID File:        {get_pid_file()}")
    print(f"  Log File:        {get_log_file()}")
    print("-" * 55)

    if creds:
        print(f"  OAuth Status:    AUTHENTICATED")
        print(f"  Google Account:  {creds.email or 'Primary User'}")
        print(f"  Project ID:      {creds.project_id or 'auto-detected'}")
        print(f"  Token Storage:   {auth_mgr.token_file}")
        if creds.expires_at:
            exp_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(creds.expires_at))
            status_text = "EXPIRED (Will auto-refresh)" if creds.is_expired() else "VALID"
            print(f"  Token Expiry:    {exp_str} [{status_text}]")
        print(f"  Refresh Token:   {'AVAILABLE' if creds.refresh_token else 'NOT FOUND'}")
    else:
        print(f"  OAuth Status:    NOT LOGGED IN")
        print(f"  Action needed:   Run 'python manage.py login'")

    print("=" * 55)
    return 0 if running and creds else 1


def cmd_login(args: argparse.Namespace) -> int:
    print("[*] Starting Google OAuth PKCE login flow for Antigravity...")
    auth_mgr = AntigravityAuthManager()
    try:
        creds = auth_mgr.login_interactive(open_browser=not args.no_browser)
        print("\n[+] Login successful!")
        print(f"    Account:    {creds.email}")
        print(f"    Project ID: {creds.project_id}")
        print(f"    Tokens:     {auth_mgr.token_file}")
        return 0
    except Exception as e:
        print(f"[-] Login failed: {e}")
        return 1


def _ensure_core_registrations() -> None:
    """Verify and ensure all core registrations for Antigravity are in place."""
    print("[*] Verifying core registrations for Antigravity (Dashboard, Models, OAuth)...")
    try:
        from hermes_cli.auth import PROVIDER_REGISTRY
        from hermes_cli.providers import HERMES_OVERLAYS
        from hermes_cli.models import _PROVIDER_MODELS, CANONICAL_PROVIDERS

        has_auth = "antigravity" in PROVIDER_REGISTRY
        has_overlay = "antigravity" in HERMES_OVERLAYS
        has_models = "antigravity" in _PROVIDER_MODELS
        has_canonical = any(p.slug == "antigravity" for p in CANONICAL_PROVIDERS)

        if has_auth and has_overlay and has_models and has_canonical:
            print("    [+] All core registries verified: Auth, Models, Overlays, and Catalog are ACTIVE.")
        else:
            print(f"    [!] Core status: Auth={has_auth}, Overlay={has_overlay}, Models={has_models}, Canonical={has_canonical}")
    except Exception as exc:
        print(f"    [!] Registry check notice: {exc}")


def cmd_install(args: argparse.Namespace) -> int:
    """Install provider plugin to ~/.hermes/plugins/model-providers/antigravity/ for upgrade survival."""
    hermes_dir = get_hermes_dir()
    dest_plugin_dir = hermes_dir / "plugins" / "model-providers" / "antigravity"
    src_plugin_dir = PLUGIN_ROOT / "plugin"
    dest_bridge_dir = hermes_dir / "bridge" / "antigravity" / "tools" / "antigravity_bridge"
    src_bridge_dir = PLUGIN_ROOT / "bridge"

    print(f"[*] Installing Antigravity provider plugin to {dest_plugin_dir}...")
    dest_plugin_dir.mkdir(parents=True, exist_ok=True)
    for item in src_plugin_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, dest_plugin_dir / item.name)
            print(f"    Copied {item.name}")

    print(f"[*] Copying bridge module to {dest_bridge_dir}...")
    dest_bridge_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_bridge_dir.exists():
        shutil.rmtree(dest_bridge_dir, ignore_errors=True)
    shutil.copytree(src_bridge_dir, dest_bridge_dir)
    print("    Copied bridge runtime engine.")

    # Also copy the manager script to ~/.hermes/bridge/antigravity/
    shutil.copy2(Path(__file__), hermes_dir / "bridge" / "antigravity" / "manage.py")
    print(f"    Copied management script to {hermes_dir / 'bridge' / 'antigravity' / 'manage.py'}")

    _ensure_core_registrations()
    print("[+] Plugin & Bridge installed! It is now permanently persistent across Hermes upgrades.")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    """Configure Hermes config.yaml and .env to use Antigravity."""
    hermes_dir = get_hermes_dir()
    config_file = hermes_dir / "config.yaml"
    env_file = hermes_dir / ".env"

    cmd_install(args)

    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_content = ""
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            env_content = f.read()

    if "ANTIGRAVITY_API_KEY" not in env_content:
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("\n# Antigravity Local OAuth Bridge Key\nANTIGRAVITY_API_KEY=antigravity-local-token\n")
        print("[+] Added ANTIGRAVITY_API_KEY to ~/.hermes/.env")

    model_name = args.model or "gemini-3.7-flash"
    port = args.port or DEFAULT_BRIDGE_PORT
    base_url = f"http://127.0.0.1:{port}/v1"

    print(f"[*] Configuring Hermes (~/.hermes/config.yaml)...")
    try:
        import yaml
        config_data = {}
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

        if "model" not in config_data or not isinstance(config_data["model"], dict):
            config_data["model"] = {}

        config_data["model"]["default"] = model_name
        config_data["model"]["provider"] = "antigravity"
        config_data["model"]["base_url"] = base_url

        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False)
        print(f"[+] Hermes configured to use Antigravity:")
        print(f"    model.provider: antigravity")
        print(f"    model.default:  {model_name}")
        print(f"    model.base_url: {base_url}")
    except Exception as e:
        print(f"[-] Failed to update config.yaml: {e}")
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity Local OAuth Bridge Manager for Hermes")
    subparsers = parser.add_subparsers(dest="action", required=True)

    p_start = subparsers.add_parser("start", help="Start the bridge server daemon")
    p_start.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT, help="Port to listen on")
    p_start.add_argument("--host", type=str, default=DEFAULT_BRIDGE_HOST, help="Host to bind")
    p_start.add_argument("--foreground", "-f", action="store_true", help="Run server in foreground")

    subparsers.add_parser("stop", help="Stop the bridge server")

    p_status = subparsers.add_parser("status", help="Show bridge and auth status")
    p_status.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT)
    p_status.add_argument("--host", type=str, default=DEFAULT_BRIDGE_HOST)

    p_login = subparsers.add_parser("login", help="Log in with Google OAuth PKCE")
    p_login.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    subparsers.add_parser("install", help="Install provider plugin to ~/.hermes/ for upgrade persistence")

    p_setup = subparsers.add_parser("setup", help="Auto-configure Hermes to use Antigravity")
    p_setup.add_argument("--model", type=str, default="gemini-3.7-flash", help="Default model name")
    p_setup.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT)

    args = parser.parse_args()

    handlers = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "login": cmd_login,
        "install": cmd_install,
        "setup": cmd_setup,
    }
    return handlers[args.action](args)


if __name__ == "__main__":
    sys.exit(main())