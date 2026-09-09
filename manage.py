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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

    runner_code = (
        f"import sys, os\n"
        f"for p in [r'{PLUGIN_ROOT}', r'{REPO_ROOT}']:\n"
        f"    if p not in sys.path: sys.path.insert(0, p)\n"
        f"try:\n"
        f"    log_fd = open(r'{log_file}', 'a', encoding='utf-8')\n"
        f"    sys.stdout = log_fd\n"
        f"    sys.stderr = log_fd\n"
        f"except Exception:\n"
        f"    pass\n"
        f"try:\n"
        f"    from bridge.server import run_server\n"
        f"except ImportError:\n"
        f"    from tools.antigravity_bridge.server import run_server\n"
        f"run_server(host='{host}', port={port})\n"
    )

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    proc = None
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", "-c", runner_code],
                creationflags=flags | 0x01000000,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                env=env,
                cwd=str(PLUGIN_ROOT),
            )
        except OSError:
            proc = subprocess.Popen(
                [sys.executable, "-u", "-c", runner_code],
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                env=env,
                cwd=str(PLUGIN_ROOT),
            )
    else:
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", runner_code],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env=env,
            cwd=str(PLUGIN_ROOT),
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
    port = getattr(args, "port", None) or DEFAULT_BRIDGE_PORT
    stopped_any = False

    # 1. Clean up known PID files across profiles
    candidate_pid_files = [
        get_pid_file(),
        Path.home() / "AppData" / "Local" / "hermes" / "bridge" / "antigravity" / "bridge.pid",
        Path.home() / ".hermes" / "bridge" / "antigravity" / "bridge.pid",
    ]
    for p_file in candidate_pid_files:
        if p_file.is_file():
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                if pid > 0:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, signal.SIGTERM)
                    print(f"[+] Stopped Antigravity Bridge (PID: {pid})")
                    stopped_any = True
            except Exception:
                pass
            p_file.unlink(missing_ok=True)

    # 2. Terminate any lingering process bound to bridge port
    try:
        import psutil
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.pid:
                try:
                    p = psutil.Process(conn.pid)
                    p.kill()
                    print(f"[+] Killed lingering process {conn.pid} on port {port}")
                    stopped_any = True
                except Exception:
                    pass
    except Exception:
        pass

    if not stopped_any:
        print(f"[*] No active bridge process was running on port {port}.")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart the Antigravity Local Bridge daemon."""
    print("[*] Restarting Antigravity Bridge...")
    cmd_stop(args)
    time.sleep(1.0)
    return cmd_start(args)


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
            status_text = "EXPIRED (Will auto-refresh)" if creds.is_expired else "VALID"
            print(f"  Token Expiry:    {exp_str} [{status_text}]")
        print(f"  Refresh Token:   {'AVAILABLE' if creds.refresh_token else 'NOT FOUND'}")
    else:
        print(f"  OAuth Status:    NOT LOGGED IN")
        print(f"  Action needed:   Run 'python manage.py login'")

    try:
        try:
            from bridge.fingerprint import AntigravityFingerprint
        except ImportError:
            from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
        f_info = AntigravityFingerprint.get_status_summary()
        print(f"  IDE Stealth:     {f_info['description']}")
    except Exception:
        pass

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
        try:
            try:
                from bridge.account_pool import AntigravityAccountPoolManager
            except ImportError:
                from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
            pool = AntigravityAccountPoolManager(storage_path=auth_mgr.auth_file)
            pool.add_or_update_account(creds)
            pool.set_active_account(creds.email)
        except Exception:
            pass
        try:
            from bridge.server import ensure_antigravity_bridge_running
            if ensure_antigravity_bridge_running():
                print("[+] Antigravity Bridge Daemon auto-started in background.")
        except Exception:
            pass
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
    """Install provider plugin across all Hermes homes, profiles, and workspaces for upgrade survival."""
    try:
        import install
        install.main()
        return 0
    except Exception as e:
        print(f"[-] Installation failed: {e}")
        return 1


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
        subprocess.run(["hermes", "config", "set", "model.provider", "antigravity"], check=True)
        subprocess.run(["hermes", "config", "set", "model.default", model_name], check=True)
        subprocess.run(["hermes", "config", "set", "model.base_url", base_url], check=True)
        print(f"[+] Hermes configured to use Antigravity:")
        print(f"    model.provider: antigravity")
        print(f"    model.default:  {model_name}")
        print(f"    model.base_url: {base_url}")
        try:
            from bridge.server import ensure_antigravity_bridge_running
            if ensure_antigravity_bridge_running(port=port):
                print(f"[+] Antigravity Bridge Daemon auto-started on {base_url}")
        except Exception:
            pass
    except Exception as e:
        print(f"[-] Failed to update config.yaml: {e}")
        return 1

    return 0


def cmd_flow_status(args: argparse.Namespace) -> int:
    """Check Google Flow Camofox session status and token health."""
    import asyncio
    try:
        from bridge.flow.flow_auth_service import FlowAuthService
    except ImportError:
        from tools.antigravity_bridge.flow.flow_auth_service import FlowAuthService

    svc = FlowAuthService.get_instance()
    st = svc.get_status()

    try:
        from bridge.flow.camofox_bridge import CamofoxFlowBridge
    except ImportError:
        from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
    bridge = CamofoxFlowBridge()
    running = bridge.is_server_running()

    print("=" * 65)
    print("           GOOGLE FLOW & CAMOFOX AUTH STATUS             ")
    print("=" * 65)
    print(f"  Connection Status:   {'[CONNECTED]' if st.get('connected') else '[DISCONNECTED]'}")
    print(f"  Email:               {st.get('email') or 'N/A'}")
    print(f"  Status Label:        {st.get('status_label')}")
    print(f"  Token Expiration:    {st.get('expires_at') or 'N/A'}")
    if st.get("expires_in_seconds"):
        rem_m = st['expires_in_seconds'] // 60
        print(f"  Remaining Time:      {rem_m} minutes")
    print(f"  Session Cookie (30d):{'PRESENT [READY FOR AUTO-REFRESH]' if st.get('has_session_cookie') else 'ABSENT'}")
    print(f"  Token Preview:       {st.get('token_preview') or 'N/A'}")
    print("-" * 65)
    print(f"  Camofox Server:      {'ONLINE' if running else 'OFFLINE (9377)'}")
    if running:
        async def _check():
            return await bridge.check_status()
        b_status = asyncio.run(_check())
        print(f"  Tab Connected:       {b_status.get('tab_connected')}")
        print(f"  Tab ID:              {b_status.get('tab_id') or 'None'}")
    print("=" * 65)
    print("Commands:")
    print("  1-Click Handshake:   python manage.py flow-handshake")
    print("  Auto-Refresh Token:  python manage.py flow-refresh")
    print("=" * 65)
    return 0


def cmd_flow_refresh(args: argparse.Namespace) -> int:
    """Test headless background auto-refresh of Google Flow token."""
    import asyncio
    try:
        from bridge.flow.flow_refresh_daemon import FlowRefreshDaemon
    except ImportError:
        from tools.antigravity_bridge.flow.flow_refresh_daemon import FlowRefreshDaemon

    print("[*] Initiating headless background auto-refresh of Google Flow token...")
    daemon = FlowRefreshDaemon.get_instance()

    async def _run():
        return await daemon._perform_headless_refresh()

    success, token = asyncio.run(_run())
    if success:
        print(f"[+] SUCCESS! Google Flow token refreshed headless. Token preview: {token[:10]}...")
        return 0
    else:
        print(f"[-] Refresh failed: {token}")
        print("    Please run 'python manage.py flow-handshake' to re-authenticate.")
        return 1


def cmd_flow_handshake(args: argparse.Namespace) -> int:
    """Launch 1-Click Visible Handshake with automatic window closing."""
    try:
        from bridge.flow.flow_auth_service import FlowAuthService
    except ImportError:
        from tools.antigravity_bridge.flow.flow_auth_service import FlowAuthService

    svc = FlowAuthService.get_instance()
    timeout = getattr(args, "timeout", None) or 300

    print("=" * 65)
    print("          GOOGLE FLOW 1-CLICK VISIBLE HANDSHAKE          ")
    print("=" * 65)
    print("[*] Khởi chạy trình duyệt đăng nhập chính diện màn hình...")
    print("    👉 Vui lòng nhấn vào tài khoản Google của bạn trên màn hình.")
    print("    Cửa sổ sẽ TỰ ĐỘNG BIẾN MẤT ngay khi đăng nhập thành công!")
    print("-" * 65)

    sess = svc.start_handshake(timeout_seconds=timeout)
    while True:
        s = svc.get_handshake_session(sess.session_id)
        if not s:
            print("[-] Phiên handshake bị mất.")
            return 1
        if s.status == "completed":
            print(f"\n[+] ĐĂNG NHẬP THÀNH CÔNG! Tài khoản: {s.email}")
            print("[+] Cửa sổ đã tự động đóng. Token & Session đã lưu.")
            return 0
        elif s.status in ("error", "timeout", "cancelled"):
            print(f"\n[-] Handshake kết thúc với trạng thái: {s.status} ({s.error_message or ''})")
            return 1
        time.sleep(1.0)


def cmd_accounts(args: argparse.Namespace) -> int:
    """Display Antigravity OAuth multi-account pool table."""
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    pool = AntigravityAccountPoolManager()
    accounts = pool.list_accounts()
    active_acc = pool.get_active_account()
    strategy = pool.get_rotation_strategy()

    mode_str = "MULTI-ACCOUNT SHARDED POOL" if len(accounts) >= 2 else "SINGLE-ACCOUNT RESILIENCE MODE"

    print("=" * 88)
    print(f"       GOOGLE ANTIGRAVITY OAUTH ACCOUNT POOL ({len(accounts)} Accounts Registered)       ")
    print(f"       Mode: {mode_str} | Strategy: {strategy.upper()}")
    print("=" * 88)
    print(f" {'EMAIL':<28} {'ROLE':<11} {'STATUS':<14} {'PROJECT':<16} {'EXPIRY':<10} {'ACTIVE'}")
    print("-" * 88)
    now = time.time()
    for acc in accounts:
        is_act = "--> [ACTIVE]" if active_acc and acc.email == active_acc.email else ""
        if acc.status in {"exhausted", "cooling_down"} and acc.exhausted_until:
            rem = max(0, int(acc.exhausted_until - now))
            st = f"COOLDOWN({rem}s)"
        elif acc.is_available:
            st = "READY"
        else:
            st = acc.status.upper()

        if acc.is_expired:
            exp_str = "Auto-ref"
        elif acc.expires_at > 0:
            m = max(0, int((acc.expires_at - now) / 60))
            exp_str = f"{m}m valid"
        else:
            exp_str = "Persistent"

        role_str = acc.assigned_role.upper()
        print(f" {acc.email:<28} {role_str:<11} {st:<14} {acc.project_id:<16} {exp_str:<10} {is_act}")
    print("=" * 88)
    print("Commands:")
    print("  Set Strategy:     python manage.py strategy [sharded|round_robin|failover]")
    print("  Assign Role:      python manage.py role <email> [all|llm|image_gen]")
    print("  Switch Active:    python manage.py account-switch <email>")
    print("  Remove Account:   python manage.py account-remove <email>")
    print("  Add/Login:        python manage.py login")
    print("=" * 88)
    return 0


def cmd_account_strategy(args: argparse.Namespace) -> int:
    """Configure rotation strategy for Antigravity OAuth accounts."""
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    pool = AntigravityAccountPoolManager()
    st = args.strategy.strip().lower()
    if pool.set_rotation_strategy(st):
        print(f"[+] Successfully updated Antigravity rotation strategy to '{st}'.")
        return 0
    else:
        print(f"[-] Invalid strategy '{st}'. Choose 'sharded', 'round_robin', or 'failover'.")
        return 1


def cmd_account_role(args: argparse.Namespace) -> int:
    """Assign service role to account ('all', 'llm', 'image_gen')."""
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    pool = AntigravityAccountPoolManager()
    email = args.email.strip().lower()
    role = args.role.strip().lower()
    if pool.set_account_role(email, role):
        print(f"[+] Successfully set role for '{email}' to '{role}'.")
        return 0
    else:
        print(f"[-] Failed to set role. Check that account '{email}' exists and role is one of: all, llm, image_gen.")
        return 1


def cmd_account_switch(args: argparse.Namespace) -> int:
    """Switch active Antigravity OAuth account."""
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    pool = AntigravityAccountPoolManager()
    target_email = args.email.strip().lower()
    if pool.set_active_account(target_email):
        print(f"[+] Successfully switched active Antigravity account to '{target_email}'.")
        return 0
    else:
        print(f"[-] Account '{target_email}' not found in pool. Run 'python manage.py accounts' to list.")
        return 1


def cmd_account_remove(args: argparse.Namespace) -> int:
    """Remove an account from Antigravity OAuth pool."""
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    pool = AntigravityAccountPoolManager()
    target_email = args.email.strip().lower()
    if pool.remove_account(target_email):
        print(f"[+] Account '{target_email}' removed from Antigravity account pool.")
        return 0
    else:
        print(f"[-] Account '{target_email}' not found in pool.")
        return 1


def cmd_account_strategy(args: argparse.Namespace) -> int:
    """Configure rotation strategy for Antigravity OAuth accounts."""
    try:
        from bridge.account_pool import AntigravityAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager

    pool = AntigravityAccountPoolManager()
    st = args.strategy.strip().lower()
    if pool.set_rotation_strategy(st):
        print(f"[+] Successfully updated Antigravity rotation strategy to '{st}'.")
        return 0
    else:
        print(f"[-] Invalid strategy '{st}'. Choose 'failover' or 'round_robin'.")
        return 1


def cmd_flow_accounts(args: argparse.Namespace) -> int:
    """Display Google Flow multi-account pool table."""
    try:
        from bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager

    pool = FlowAccountPoolManager()
    accounts = pool.list_accounts()
    active_acc = pool.get_active_account()

    print("=" * 72)
    print("                 GOOGLE FLOW MULTI-ACCOUNT POOL                 ")
    print("=" * 72)
    print(f" {'ID':<12} {'STATUS':<14} {'EMAIL':<26} {'TOTAL':<8} {'ACTIVE'}")
    print("-" * 72)
    for acc in accounts:
        is_act = "--> [ACTIVE]" if acc.id == active_acc.id else ""
        st = acc.status.upper()
        if acc.status == "exhausted" and acc.exhausted_until:
            m = max(0, int((acc.exhausted_until - time.time()) / 60))
            st = f"EXHAUSTED({m}m)"
        em = (acc.email or acc.label or "N/A")[:25]
        print(f" {acc.id:<12} {st:<14} {em:<26} {acc.total_creations:<8} {is_act}")
    print("=" * 72)
    print("Commands:")
    print("  Add/Login Account:   python manage.py flow-login --account <id>")
    print("  Switch Active:       python manage.py flow-switch <id>")
    print("  Remove Account:      python manage.py flow-remove <id>")
    print("=" * 72)
    return 0


def cmd_flow_switch(args: argparse.Namespace) -> int:
    """Switch active Google Flow account in pool."""
    try:
        from bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager

    pool = FlowAccountPoolManager()
    target_id = args.account_id.strip().lower()
    if pool.set_active_account(target_id):
        print(f"[+] Successfully switched active Google Flow account to '{target_id}'.")
        return 0
    else:
        print(f"[-] Account '{target_id}' not found in pool. Run 'python manage.py flow-accounts' to list.")
        return 1


def cmd_flow_remove(args: argparse.Namespace) -> int:
    """Remove an account from pool."""
    try:
        from bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager

    pool = FlowAccountPoolManager()
    target_id = args.account_id.strip().lower()
    if pool.remove_account(target_id):
        print(f"[+] Account '{target_id}' removed from pool.")
        return 0
    else:
        print(f"[-] Account '{target_id}' not found in pool.")
        return 1


def _find_camoufox_executable() -> Optional[Path]:
    """Locate installed Camoufox browser binary."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "camoufox" / "camoufox" / "Cache" / "camoufox.exe",
        Path.home() / "AppData" / "Local" / "camoufox" / "camoufox" / "Cache" / "camoufox.exe",
        Path.home() / "AppData" / "Roaming" / "Python" / "Python314" / "Scripts" / "camoufox.exe",
        Path.home() / ".cache" / "camoufox" / "camoufox.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def cmd_flow_login(args: argparse.Namespace) -> int:
    """Launch visible browser window for Google Flow login."""
    account_id = getattr(args, "account", None) or "default"
    label = getattr(args, "label", None) or ""

    try:
        from bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager

    pool = FlowAccountPoolManager()
    acc = pool.add_or_update_account(account_id, label=label)
    pool.set_active_account(acc.id)

    try:
        from playwright.sync_api import sync_playwright
        profile_dir = Path.home() / ".hermes" / "flow_browser_session"
        profile_dir.mkdir(parents=True, exist_ok=True)
        storage_path = Path.home() / ".camofox" / "profiles" / "0cd86c0f4c201630fbae6d30acc81391" / "storage-state.json"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path_def = Path.home() / ".camofox" / "profiles" / "default" / "storage-state.json"
        storage_path_def.parent.mkdir(parents=True, exist_ok=True)

        print("[*] Đang khởi chạy trình duyệt trên màn hình desktop của bạn...")
        with sync_playwright() as p:
            try:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    channel="chrome",
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                    viewport=None,
                )
            except Exception:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=False,
                    args=["--start-maximized"],
                    viewport=None,
                )

            try:
                page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            print("[+] CỬA SỔ TRÌNH DUYỆT ĐÃ MỞ TRÊN MÀN HÌNH!")
            print("    👉 Vui lòng đăng nhập tài khoản Google của bạn trên cửa sổ Chrome vừa mở.")
            print("    👉 Sau khi đăng nhập và được chuyển về giao diện Google Flow, cửa sổ sẽ tự động lưu cấu hình và đóng lại.")
            print("    Hệ thống đang tự động theo dõi phiên xác thực...")

            start = time.time()
            while time.time() - start < 360:
                try:
                    token = None
                    email = None
                    err = None
                    session_raw = None
                    try:
                        for p_tab in reversed(ctx.pages):
                            try:
                                if "labs.google" in p_tab.url:
                                    session_data = p_tab.evaluate("() => fetch('/fx/api/auth/session').then(r => r.json()).catch(() => null)")
                                    if session_data and isinstance(session_data, dict):
                                        token = session_data.get("access_token") or session_data.get("accessToken") or session_data.get("token")
                                        email = session_data.get("user", {}).get("email")
                                        err = session_data.get("error")
                                        session_raw = session_data
                                        if token and email and not err:
                                            break
                            except Exception:
                                pass
                        if not token and ctx.pages:
                            session_data = ctx.pages[-1].evaluate("() => fetch('/fx/api/auth/session').then(r => r.json()).catch(() => null)")
                            if session_data and isinstance(session_data, dict):
                                token = session_data.get("access_token") or session_data.get("accessToken") or session_data.get("token")
                                email = session_data.get("user", {}).get("email")
                                err = session_data.get("error")
                                session_raw = session_data
                    except Exception:
                        pass

                    # Require genuine OAuth access token and email without error
                    if token and email and not err and (token.startswith("ya29.") or len(token) > 40) and not token.startswith("flow_session"):
                        ctx.storage_state(path=str(storage_path))
                        ctx.storage_state(path=str(storage_path_def))
                        email_str = email
                        pool.add_or_update_account(acc.id, email=email_str, status="active")

                        payload = {
                            "token": token,
                            "access_token": token,
                            "email": email_str,
                            "updated_at": time.time(),
                            "expires": session_raw.get("expires") if session_raw else None,
                            "user": session_raw.get("user") if session_raw else {"email": email_str},
                        }
                        raw_json = json.dumps(payload, indent=2)

                        # Write to all standard locations across Hermes and Camofox
                        for target_f in [
                            Path.home() / ".hermes" / "auth" / "flow_token.json",
                            Path.home() / ".hermes" / "flow_token.json",
                            Path.home() / "AppData" / "Local" / "hermes" / "auth" / "flow_token.json",
                            Path.home() / ".camofox" / "flow_token.json",
                        ]:
                            try:
                                target_f.parent.mkdir(parents=True, exist_ok=True)
                                target_f.write_text(raw_json, encoding="utf-8")
                            except Exception:
                                pass

                        print(f"\n[+] ĐĂNG NHẬP GOOGLE FLOW THÀNH CÔNG! Tài khoản: '{email_str}'")
                        print(f"[+] Access Token hợp lệ: {token[:15]}... (đã lưu vào hệ thống)")
                        print(f"[+] Toàn bộ Cookies & Session đã được đồng bộ an toàn vào Camofox Profile!")
                        time.sleep(2)
                        ctx.close()
                        return 0
                except Exception:
                    pass
                time.sleep(2.0)

            print("\n[-] Quá thời gian chờ đăng nhập (Timeout 360s).")
            ctx.close()
            return 1
    except Exception as e:
        print(f"[-] Lỗi: {e}")
        return 1



def cmd_models(args: argparse.Namespace) -> int:
    """List all available models discovered dynamically from Antigravity IDE / Code Assist."""
    try:
        from bridge.models import ModelDiscoveryManager
    except ImportError:
        from tools.antigravity_bridge.models import ModelDiscoveryManager

    mgr = ModelDiscoveryManager()
    force_refresh = getattr(args, "refresh", False)
    models = mgr.get_discovered_models(force_refresh=force_refresh)

    print("=" * 85)
    print(f"   ANTIGRAVITY MODEL CATALOGUE ({len(models)} Models Discovered)   ")
    print("=" * 85)
    print(f"{'MODEL ID':<28} | {'DISPLAY NAME':<26} | {'QUOTA':<8} | {'CONTEXT':<9} | {'THINKING'}")
    print("-" * 85)

    for m in models:
        quota_str = f"{int(m.quota_fraction * 100)}%" if m.quota_fraction is not None else "--"
        rec = " *" if m.recommended else ""
        thk = f"Yes ({m.thinking_budget}t)" if m.supports_thinking else "No"
        ctx = f"{m.max_tokens // 1024}k" if m.max_tokens >= 1024 else str(m.max_tokens)
        print(f"{m.id:<28} | {m.display_name[:26]:<26} | {quota_str:<8} | {ctx:<9} | {thk}{rec}")

    print("-" * 85)
    print("  * = Recommended model by Google DeepMind / Code Assist")
    print("=" * 85)
    return 0


def cmd_quota(args: argparse.Namespace) -> int:
    """Display quota summary from Google Code Assist API."""
    try:
        from bridge.models import ModelDiscoveryManager
    except ImportError:
        from tools.antigravity_bridge.models import ModelDiscoveryManager

    mgr = ModelDiscoveryManager()
    force_refresh = getattr(args, "refresh", False)
    summary = mgr.fetch_quota_summary(force_refresh=force_refresh)

    groups = summary.get("groups", [])
    print("=" * 70)
    print("         GOOGLE ANTIGRAVITY QUOTA & RATE LIMIT REPORT         ")
    print("=" * 70)

    if not groups:
        print("  [INFO] No quota summary returned. You may be on standard unmetered tier.")
    else:
        for grp in groups:
            name = grp.get("displayName") or "Group"
            desc = grp.get("description") or ""
            print(f"\n[GROUP: {name.upper()}] - {desc}")
            for b in grp.get("buckets", []):
                b_name = b.get("displayName") or b.get("bucketId")
                rem = b.get("remainingFraction", 0)
                rem_pct = f"{rem * 100:.1f}%"
                reset = b.get("resetTime") or "N/A"
                print(f"  • {b_name:<30} Remaining: {rem_pct:<8} (Reset: {reset})")
                if b.get("description"):
                    print(f"    Note: {b.get('description')}")

    print("\n" + "=" * 70)
    return 0

def cmd_doctor(args: argparse.Namespace) -> int:
    """Run comprehensive health checks and self-diagnostics."""
    import asyncio
    print("=" * 65)
    print("      HERMES ANTIGRAVITY & GOOGLE FLOW DOCTOR REPORT     ")
    print("=" * 65)

    all_good = True
    hermes_dir = get_hermes_dir()

    # 1. Antigravity Auth Check
    auth_mgr = AntigravityAuthManager()
    creds = auth_mgr.load_stored_credentials()
    if creds and not creds.is_expired:
        print("  [OK] Antigravity OAuth:       AUTHENTICATED")
        print(f"       Account:                 {creds.email or 'Primary User'}")
    elif creds and creds.is_expired:
        if creds.refresh_token:
            print("  [OK] Antigravity OAuth:       EXPIRED (Auto-refresh token available)")
        else:
            print("  [WARN] Antigravity OAuth:     EXPIRED (No refresh token)")
            all_good = False
    else:
        print("  [WARN] Antigravity OAuth:     NOT LOGGED IN (Run 'python manage.py login')")
        all_good = False

    # 1b. Antigravity Multi-Account Pool Check
    try:
        try:
            from bridge.account_pool import AntigravityAccountPoolManager
        except ImportError:
            from tools.antigravity_bridge.account_pool import AntigravityAccountPoolManager
        ag_pool = AntigravityAccountPoolManager()
        ag_accs = ag_pool.list_accounts()
        ag_active = ag_pool.get_active_account()
        ag_avail = sum(1 for a in ag_accs if a.is_available)
        ag_strat = ag_pool.get_rotation_strategy()
        act_email = ag_active.email if ag_active else "None"
        print(f"  [OK] Antigravity Accounts:    {len(ag_accs)} accounts ({ag_avail} ready, active: '{act_email}', strategy: {ag_strat})")
    except Exception as ex:
        print(f"  [WARN] Antigravity Accounts:  {ex}")

    # 2. Antigravity Bridge Daemon Check
    port = getattr(args, "port", None) or DEFAULT_BRIDGE_PORT
    host = getattr(args, "host", None) or DEFAULT_BRIDGE_HOST
    bridge_running = is_server_running(host, port)
    if not bridge_running and creds and not creds.is_expired:
        try:
            from bridge.server import ensure_antigravity_bridge_running
            if ensure_antigravity_bridge_running(host=host, port=port, timeout=3.0):
                bridge_running = True
        except Exception:
            pass

    if bridge_running:
        print(f"  [OK] Bridge Daemon:           ONLINE (http://{host}:{port}/v1)")
    else:
        print(f"  [INFO] Bridge Daemon:         STANDBY (Auto-starts on demand or 'python manage.py start')")

    # 3. Google Flow & Camofox Engine Check
    try:
        from bridge.flow.camofox_bridge import CamofoxFlowBridge
        from bridge.flow.account_pool import FlowAccountPoolManager
    except ImportError:
        from tools.antigravity_bridge.flow.camofox_bridge import CamofoxFlowBridge
        from tools.antigravity_bridge.flow.account_pool import FlowAccountPoolManager

    c_bridge = CamofoxFlowBridge()
    c_running = c_bridge.is_server_running()
    if c_running:
        print("  [OK] Camofox Server:          ONLINE (http://127.0.0.1:9377)")
    else:
        print("  [INFO] Camofox Server:        STANDBY (Auto-launches on first Flow generation)")

    # 4. Multi-Account Pool Check
    try:
        pool = FlowAccountPoolManager()
        accounts = pool.list_accounts()
        active_acc = pool.get_active_account()
        avail = sum(1 for a in accounts if a.is_available)
        print(f"  [OK] Flow Account Pool:       {len(accounts)} accounts ({avail} ready, active: '{active_acc.id}')")
    except Exception as ex:
        print(f"  [WARN] Flow Account Pool:     {ex}")

    # 5. Dynamic Model Discovery & Quota Check
    try:
        try:
            from bridge.models import ModelDiscoveryManager
        except ImportError:
            from tools.antigravity_bridge.models import ModelDiscoveryManager
        dmgr = ModelDiscoveryManager()
        disc_models = dmgr.get_discovered_models(force_refresh=False)
        claude_m = next((m for m in disc_models if "claude" in m.id), None)
        c_quota = f", Claude: {int(claude_m.quota_fraction * 100)}%" if claude_m and claude_m.quota_fraction is not None else ""
        print(f"  [OK] Model Discovery:         {len(disc_models)} models discovered{c_quota}")
    except Exception as ex:
        print(f"  [WARN] Model Discovery:       OFFLINE ({ex})")

    # 6. IDE Stealth & Anti-Detection Fingerprint Check
    try:
        try:
            from bridge.fingerprint import AntigravityFingerprint
        except ImportError:
            from tools.antigravity_bridge.fingerprint import AntigravityFingerprint
        f_info = AntigravityFingerprint.get_status_summary()
        if f_info.get("is_local_binary"):
            print(f"  [OK] IDE Simulation:          v{f_info['version']} (Synced with Local IDE)")
        else:
            print(f"  [OK] IDE Simulation:          v{f_info['version']} (Autonomous Built-in Profile)")
    except Exception as ex:
        print(f"  [WARN] IDE Simulation:        DEFAULT ({ex})")

    # 7. File Synchronization & Upgrade Persistence Check
    dest_plugin = hermes_dir / "plugins" / "model-providers" / "antigravity" / "injector.py"
    dest_bridge = hermes_dir / "bridge" / "antigravity" / "tools" / "antigravity_bridge" / "flow" / "account_pool.py"
    if dest_plugin.exists() and dest_bridge.exists():
        print("  [OK] Upgrade Persistence:     INSTALLED in ~/.hermes/ (Survives Hermes updates)")
    else:
        print("  [WARN] Upgrade Persistence:   PARTIAL (Run 'python manage.py install' to sync)")
        all_good = False

    # 6. Dashboard Runtime Injection Health
    try:
        from plugin.injector import get_injection_health
        h = get_injection_health()
        if h.get("web_server_detected"):
            print("  [OK] Dashboard Hooks:         ACTIVE (Web Server running and patched)")
        else:
            print("  [INFO] Dashboard Hooks:       STANDBY (Will auto-inject when 'hermes dashboard' starts)")
    except Exception:
        pass

    print("-" * 65)
    if all_good:
        print("  STATUS: SYSTEM HEALTHY - READY FOR AGENT OPERATIONS")
    else:
        print("  STATUS: ACTION RECOMMENDED - See warnings above")
    print("=" * 65)
    return 0


def cmd_image(args: argparse.Namespace) -> int:
    """Generate an image using Gemini 3.1 Flash Image via Antigravity OAuth."""
    prompt = args.prompt
    aspect = args.aspect or "16:9"
    print(f"[*] Generating image via Gemini 3.1 Flash Image...")
    print(f"    Prompt:       {prompt}")
    print(f"    Aspect Ratio: {aspect}")
    try:
        from image_gen.antigravity import AntigravityImageGenProvider
    except ImportError:
        from plugins.image_gen.antigravity import AntigravityImageGenProvider

    p = AntigravityImageGenProvider()
    res = p.generate(prompt, aspect_ratio=aspect)
    if res.get("success"):
        img_path = res.get("image")
        size_bytes = os.path.getsize(img_path) if img_path and os.path.exists(img_path) else 0
        print(f"[+] Image generated successfully!")
        print(f"    Path:   {img_path}")
        print(f"    Model:  {res.get('model')}")
        print(f"    Size:   {size_bytes:,} bytes")
        return 0
    else:
        print(f"[-] Generation failed: {res.get('error')}")
        return 1


def cmd_video_model(args: argparse.Namespace) -> int:
    """View or set the default Google Flow video generation model in config.yaml."""
    from video_gen.antigravity import VEO_MODELS
    import yaml

    cfg_file = get_hermes_dir() / "config.yaml"
    current_model = "omni-1.1-flash"
    if cfg_file.is_file():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            current_model = data.get("video_gen", {}).get("model") or "omni-1.1-flash"
        except Exception:
            pass

    if getattr(args, "set_model", None):
        target = args.set_model.strip().lower()
        matched = next((m for m in VEO_MODELS if m["id"] == target or target in [a.lower() for a in m.get("aliases", [])]), None)
        if not matched:
            print(f"[-] Model không hợp lệ: '{target}'")
            print("    Các model khả dụng: " + ", ".join(m["id"] for m in VEO_MODELS[:3]))
            return 1

        target_id = matched["id"]
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data.setdefault("video_gen", {})["model"] = target_id
            data.setdefault("video_gen", {})["provider"] = "antigravity"
            with open(cfg_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False)
            print(f"[+] Đã cập nhật mô hình tạo video mặc định thành: {matched['display']}")
            print(f"    File cấu hình: {cfg_file}")
            return 0
        except Exception as e:
            print(f"[-] Lỗi khi lưu cấu hình: {e}")
            return 1

    print("\n" + "=" * 68)
    print("   CÁC MÔ HÌNH TẠO VIDEO GOOGLE FLOW (5 MỨC TIÊU CHUẨN)")
    print("=" * 68)
    print(f"  Mô hình hiện tại đang dùng: \033[92m{current_model}\033[0m\n")
    for idx, m in enumerate(VEO_MODELS[:5], 1):
        is_active = " \033[92m[ĐANG CHỌN]\033[0m" if m["id"] == current_model else ""
        tier = m.get("tier", "")
        print(f"  [{idx}] \033[1m{m['display']}\033[0m{is_active}")
        print(f"      • Nhóm: {tier} | ID: {m['id']}")
        print(f"      • Chi phí: {m.get('credits', '?')} tín dụng AI/video | Tốc độ: {m['speed']}")
        print(f"      • Mục đích: {m['strengths']}\n")

    print("-" * 68)
    print("Cách đổi mô hình:")
    print("  1. Dùng lệnh CLI:   python manage.py video-model set <model_id>")
    print("  2. Trong câu lệnh:  'Tạo video bằng mô hình Veo 3.1 Fast...'")
    print("  3. Trong file:      Sửa key 'video_gen.model' trong config.yaml")
    print("=" * 68 + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity Local OAuth Bridge Manager for Hermes")
    subparsers = parser.add_subparsers(dest="action", required=True)

    p_models = subparsers.add_parser("models", help="List all LLM models dynamically discovered in Antigravity")
    p_models.add_argument("--refresh", action="store_true", help="Bust cache and fetch fresh from Code Assist API")

    p_quota = subparsers.add_parser("quota", help="Check detailed quota summary for Gemini and 3P models")
    p_quota.add_argument("--refresh", action="store_true", help="Bust cache and fetch fresh quota")

    p_doctor = subparsers.add_parser("doctor", help="Run comprehensive health checks and self-diagnostics")
    p_doctor.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT)
    p_doctor.add_argument("--host", type=str, default=DEFAULT_BRIDGE_HOST)

    p_start = subparsers.add_parser("start", help="Start the bridge server daemon")
    p_start.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT, help="Port to listen on")
    p_start.add_argument("--host", type=str, default=DEFAULT_BRIDGE_HOST, help="Host to bind")
    p_start.add_argument("--foreground", "-f", action="store_true", help="Run server in foreground")

    subparsers.add_parser("stop", help="Stop the bridge server")

    p_restart = subparsers.add_parser("restart", help="Restart the bridge server daemon")
    p_restart.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT, help="Port to listen on")
    p_restart.add_argument("--host", type=str, default=DEFAULT_BRIDGE_HOST, help="Host to bind")

    p_status = subparsers.add_parser("status", help="Show bridge and auth status")
    p_status.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT)
    p_status.add_argument("--host", type=str, default=DEFAULT_BRIDGE_HOST)

    p_login = subparsers.add_parser("login", help="Log in with Google OAuth PKCE")
    p_login.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    subparsers.add_parser("accounts", help="List all Antigravity OAuth accounts in the pool")

    p_aswitch = subparsers.add_parser("account-switch", help="Switch active Antigravity OAuth account")
    p_aswitch.add_argument("email", type=str, help="Email address of the account to set as active")

    p_arem = subparsers.add_parser("account-remove", help="Remove an account from the Antigravity OAuth pool")
    p_arem.add_argument("email", type=str, help="Email address of the account to remove")

    for alias in ["account-strategy", "strategy"]:
        p_astrat = subparsers.add_parser(alias, help="Configure rotation strategy ('sharded', 'round_robin', or 'failover')")
        p_astrat.add_argument("strategy", type=str, choices=["sharded", "round_robin", "failover"], help="Strategy: sharded, round_robin, or failover")

    for alias in ["account-role", "role"]:
        p_arole = subparsers.add_parser(alias, help="Assign service role to an account ('all', 'llm', 'image_gen')")
        p_arole.add_argument("email", type=str, help="Email address of the account")
        p_arole.add_argument("role", type=str, choices=["all", "llm", "image_gen"], help="Role: all, llm, or image_gen")

    subparsers.add_parser("flow-status", help="Check Google Flow Camofox session status")
    subparsers.add_parser("flow-refresh", help="Test headless background auto-refresh of Google Flow token")
    p_fhandshake = subparsers.add_parser("flow-handshake", help="Launch 1-Click Visible Handshake with automatic window closing")
    p_fhandshake.add_argument("--timeout", type=int, default=180, help="Timeout in seconds")
    subparsers.add_parser("flow-accounts", help="List all accounts in the Google Flow multi-account pool")

    p_flogin = subparsers.add_parser("flow-login", help="Open Camofox desktop browser to sign in to Google Flow")
    p_flogin.add_argument("--account", type=str, default="default", help="Account identifier (e.g. default, acc_2, work)")
    p_flogin.add_argument("--label", type=str, default="", help="Label for this account")

    p_fswitch = subparsers.add_parser("flow-switch", help="Switch active Google Flow account")
    p_fswitch.add_argument("account_id", type=str, help="Account ID to set as active")

    p_frem = subparsers.add_parser("flow-remove", help="Remove an account from the pool")
    p_frem.add_argument("account_id", type=str, help="Account ID to remove")

    subparsers.add_parser("install", help="Install provider plugin across all Hermes homes & profiles for upgrade persistence")
    subparsers.add_parser("sync", help="Synchronize plugin across all Hermes profiles, homes, and workspaces")

    p_setup = subparsers.add_parser("setup", help="Auto-configure Hermes to use Antigravity")
    p_setup.add_argument("--model", type=str, default="gemini-3.7-flash", help="Default model name")
    p_setup.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT)

    p_img = subparsers.add_parser("image", help="Generate an image using Gemini 3.1 Flash Image")
    p_img.add_argument("prompt", type=str, help="Image description prompt")
    p_img.add_argument("--aspect", type=str, default="16:9", choices=["1:1", "16:9", "9:16", "4:3", "3:4"], help="Aspect ratio")

    p_vmodel = subparsers.add_parser("video-model", help="View or set the default Google Flow video generation model")
    p_vmodel.add_argument("set_model", nargs="?", default=None, help="Set model ID (e.g. omni-1.1-flash, veo-3.1-lite, veo-3.1-fast)")

    args = parser.parse_args()

    handlers = {
        "models": cmd_models,
        "quota": cmd_quota,
        "doctor": cmd_doctor,
        "image": cmd_image,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "login": cmd_login,
        "accounts": cmd_accounts,
        "account-switch": cmd_account_switch,
        "account-remove": cmd_account_remove,
        "account-strategy": cmd_account_strategy,
        "strategy": cmd_account_strategy,
        "account-role": cmd_account_role,
        "role": cmd_account_role,
        "flow-status": cmd_flow_status,
        "flow-refresh": cmd_flow_refresh,
        "flow-handshake": cmd_flow_handshake,
        "flow-accounts": cmd_flow_accounts,
        "flow-login": cmd_flow_login,
        "flow-switch": cmd_flow_switch,
        "flow-remove": cmd_flow_remove,
        "video-model": cmd_video_model,
        "install": cmd_install,
        "sync": cmd_install,
        "setup": cmd_setup,
    }
    return handlers[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
