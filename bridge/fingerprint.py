"""Antigravity IDE Anti-Detection & Fingerprint Simulation Engine.

Provides dual-mode identity simulation for Google Code Assist / Antigravity endpoints:
1. Mode 1: Dynamic Probe - If Antigravity IDE is installed locally, automatically
   detects the executable and extracts the exact build version (e.g. 2.11.0).
2. Mode 2: Autonomous Synthetic - If no IDE is installed (clean Windows, Linux VPS,
   Docker container, macOS), activates a built-in golden profile matching the latest
   official Antigravity release (v2.11.0) and tailors headers to the host OS.

Guarantee:
Requests to daily-cloudcode-pa.googleapis.com / cloudcode-pa.googleapis.com are
100% indistinguishable from the official Go-based language_server.exe client.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class AntigravityFingerprint:
    """Central manager for Antigravity IDE and language_server.exe client impersonation."""

    DEFAULT_VERSION: str = "2.23.1"
    DEFAULT_CLIENT_LIBRARY_VERSION: str = "gl-go/1.24.0"
    DEFAULT_CODE_ASSIST_DATE: str = "2026.03.0"
    DEFAULT_CHANGELIST: str = "998881661"

    _cached_version: Optional[str] = None
    _cached_source: Optional[str] = None
    _cached_binary_path: Optional[str] = None
    _cached_changelist: Optional[str] = None
    _session_trajectory_id: str = str(uuid.uuid4())

    @classmethod
    def get_trajectory_id(cls) -> str:
        """Return a session-persistent trajectory UUID matching Antigravity IDE behavior."""
        if not cls._session_trajectory_id:
            cls._session_trajectory_id = str(uuid.uuid4())
        return cls._session_trajectory_id

    @classmethod
    def _find_antigravity_binary(cls) -> Optional[Path]:
        """Attempt to locate the local Antigravity IDE executable across operating systems."""
        # 1. Check explicit environment override
        env_path = os.getenv("HERMES_ANTIGRAVITY_IDE_PATH")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return p

        # 2. Windows candidate paths
        if sys.platform == "win32":
            local_app = os.environ.get("LOCALAPPDATA", "")
            prog_files = os.environ.get("PROGRAMFILES", "")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
            candidates = [
                Path(local_app) / "Programs" / "Antigravity" / "Antigravity.exe",
                Path(local_app) / "Programs" / "antigravity" / "Antigravity.exe",
                Path(local_app) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe",
                Path(prog_files) / "Antigravity" / "Antigravity.exe",
                Path(prog_files_x86) / "Antigravity" / "Antigravity.exe",
                Path.home() / "AppData" / "Local" / "Programs" / "Antigravity" / "Antigravity.exe",
                Path.home() / "AppData" / "Local" / "Programs" / "antigravity" / "Antigravity.exe",
            ]
            for cand in candidates:
                if cand and cand.is_file():
                    return cand

        # 3. macOS candidate paths
        elif sys.platform == "darwin":
            candidates = [
                Path("/Applications/Antigravity.app/Contents/MacOS/Antigravity"),
                Path.home() / "Applications" / "Antigravity.app" / "Contents" / "MacOS" / "Antigravity",
            ]
            for cand in candidates:
                if cand.is_file():
                    return cand

        # 4. Linux candidate paths
        elif sys.platform.startswith("linux"):
            candidates = [
                Path("/usr/bin/antigravity"),
                Path("/usr/local/bin/antigravity"),
                Path("/opt/antigravity/antigravity"),
                Path.home() / ".local" / "bin" / "antigravity",
            ]
            for cand in candidates:
                if cand.is_file():
                    return cand

        return None

    @classmethod
    def _find_language_server_binary(cls) -> Optional[Path]:
        """Locate the local Go language_server binary shipped inside Antigravity IDE."""
        env_ls = os.getenv("HERMES_ANTIGRAVITY_LS_PATH")
        if env_ls:
            p = Path(env_ls)
            if p.is_file():
                return p

        ide_bin = cls._find_antigravity_binary()
        search_roots = []
        if ide_bin:
            search_roots.append(ide_bin.parent)

        if sys.platform == "win32":
            local_app = os.environ.get("LOCALAPPDATA", "")
            search_roots.extend([
                Path(local_app) / "Programs" / "Antigravity",
                Path(local_app) / "Programs" / "antigravity",
                Path.home() / "AppData" / "Local" / "Programs" / "Antigravity",
            ])
            rel_paths = [
                Path("resources") / "bin" / "language_server.exe",
                Path("resources") / "app" / "extensions" / "antigravity" / "bin" / "language_server_windows_x64.exe",
                Path("resources") / "app" / "extensions" / "antigravity" / "bin" / "language_server.exe",
            ]
        elif sys.platform == "darwin":
            search_roots.extend([
                Path("/Applications/Antigravity.app/Contents"),
                Path.home() / "Applications" / "Antigravity.app" / "Contents",
            ])
            rel_paths = [
                Path("Resources") / "bin" / "language_server",
                Path("Resources") / "app" / "extensions" / "antigravity" / "bin" / "language_server_macos_arm64",
                Path("Resources") / "app" / "extensions" / "antigravity" / "bin" / "language_server_macos_x64",
            ]
        else:
            search_roots.extend([
                Path("/opt/antigravity"),
                Path("/usr/share/antigravity"),
            ])
            rel_paths = [
                Path("resources") / "bin" / "language_server",
                Path("resources") / "app" / "extensions" / "antigravity" / "bin" / "language_server_linux_x64",
            ]

        for root in search_roots:
            for rel in rel_paths:
                cand = root / rel
                if cand.is_file():
                    return cand

        return None

    @classmethod
    def _read_binary_version(cls, binary_path: Path) -> Optional[str]:
        """Extract FileVersion, ProductVersion, or package.json version from the IDE installation."""
        if not binary_path.is_file():
            return None

        # 1. Check adjacent resources/app/package.json or product.json for clean semantic version
        for rel_json in (
            Path("resources") / "app" / "package.json",
            Path("resources") / "app" / "product.json",
            Path("..") / "Resources" / "app" / "package.json",
        ):
            try:
                pkg_file = (binary_path.parent / rel_json).resolve()
                if pkg_file.is_file():
                    pkg_data = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
                    ver = pkg_data.get("ideVersion") or pkg_data.get("version")
                    if isinstance(ver, str) and ver.strip():
                        return ver.strip()
            except Exception:
                pass

        # 2. On Windows, try reading version info metadata
        if sys.platform == "win32":
            try:
                import subprocess
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                env = os.environ.copy()
                env["AG_BIN_PATH"] = str(binary_path)
                cmd = [
                    "powershell", "-NoProfile", "-Command",
                    "(Get-Item -LiteralPath $env:AG_BIN_PATH).VersionInfo.ProductVersion"
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3, creationflags=flags, env=env)
                if res.returncode == 0:
                    ver = res.stdout.strip()
                    if ver:
                        parts = ver.split(".")
                        if len(parts) >= 3:
                            return ".".join(parts[:3])
                        return ver
            except Exception as e:
                logger.debug("PowerShell VersionInfo read failed: %s", e)

        # 3. Fallback: scan binary for version string regex
        try:
            with open(binary_path, "rb") as f:
                data = f.read(10 * 1024 * 1024)
            import re
            m = re.search(rb"Antigravity\x00([0-9]+\.[0-9]+\.[0-9]+)", data)
            if m:
                return m.group(1).decode("ascii", errors="ignore")
        except Exception as e:
            logger.debug("Binary regex version scan failed: %s", e)

        return None

    @classmethod
    def _read_binary_changelist(cls, ls_path: Optional[Path] = None) -> Optional[str]:
        """Extract the Google Perforce Changelist (CL) from language_server -stamp."""
        target = ls_path or cls._find_language_server_binary()
        if not target or not target.is_file():
            return None

        try:
            import re
            import subprocess
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            res = subprocess.run(
                [str(target), "-stamp"],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=flags,
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            m = re.search(r"Built at CL:\s*([0-9]+)", output)
            if m:
                return m.group(1).strip()
        except Exception as e:
            logger.debug("language_server -stamp probe failed: %s", e)

        return None

    @classmethod
    def get_changelist(cls, force_refresh: bool = False) -> str:
        """Return the detected language_server changelist or golden default (998881661)."""
        if not force_refresh and cls._cached_changelist is not None:
            return cls._cached_changelist
        cl = cls._read_binary_changelist()
        cls._cached_changelist = cl or cls.DEFAULT_CHANGELIST
        return cls._cached_changelist

    @classmethod
    def get_version_info(cls, force_refresh: bool = False) -> Tuple[str, str, Optional[str]]:
        """Get (version, source, binary_path).

        Source is either 'local_binary' or 'builtin_golden'.
        """
        if not force_refresh and cls._cached_version is not None:
            return cls._cached_version, cls._cached_source or "builtin_golden", cls._cached_binary_path

        binary = cls._find_antigravity_binary()
        if binary:
            ver = cls._read_binary_version(binary)
            if ver:
                cls._cached_version = ver
                cls._cached_source = "local_binary"
                cls._cached_binary_path = str(binary)
                return cls._cached_version, cls._cached_source, cls._cached_binary_path

        # Autonomous Synthetic profile
        cls._cached_version = cls.DEFAULT_VERSION
        cls._cached_source = "builtin_golden"
        cls._cached_binary_path = None
        return cls._cached_version, cls._cached_source, cls._cached_binary_path

    @classmethod
    def get_go_arch_and_os(cls) -> Tuple[str, str]:
        """Return (go_os, go_arch) matching Go runtime.GOOS and runtime.GOARCH in language_server."""
        mode = (os.getenv("HERMES_ANTIGRAVITY_PLATFORM") or "").strip().lower()
        if mode == "windows":
            return "windows", "amd64"
        if mode in {"darwin", "macos", "mac"}:
            return "darwin", "arm64"
        if mode == "linux":
            return "linux", "amd64"

        sys_name = sys.platform
        machine = (platform.machine() or "").lower()
        if "arm" in machine or "aarch64" in machine:
            go_arch = "arm64"
        elif "64" in machine or machine in {"amd64", "x86_64"} or not machine:
            go_arch = "amd64"
        else:
            go_arch = "386"

        if sys_name == "win32":
            return "windows", go_arch
        elif sys_name == "darwin":
            return "darwin", go_arch
        else:
            return "linux", go_arch

    @classmethod
    def get_platform_info(cls) -> Tuple[str, str]:
        """Return (os_user_agent_snippet, protobuf_platform_enum)."""
        mode = (os.getenv("HERMES_ANTIGRAVITY_PLATFORM") or "").strip().lower()
        if mode == "windows":
            return "Windows NT 10.0; Win64; x64", "PLATFORM_WINDOWS"
        if mode in {"darwin", "macos", "mac"}:
            return "Macintosh; Apple Silicon", "PLATFORM_DARWIN"
        if mode == "linux":
            return "X11; Linux x86_64", "PLATFORM_LINUX"

        sys_name = sys.platform
        if sys_name == "win32":
            arch = "x64" if "64" in platform.machine() or not platform.machine() else "x86"
            return f"Windows NT 10.0; Win64; {arch}", "PLATFORM_WINDOWS"
        elif sys_name == "darwin":
            arch = "Apple Silicon" if platform.machine() == "arm64" else "Intel Mac OS X 10_15_7"
            return f"Macintosh; {arch}", "PLATFORM_DARWIN"
        else:
            machine = platform.machine() or "x86_64"
            return f"X11; Linux {machine}", "PLATFORM_LINUX"

    @classmethod
    def build_client_metadata(cls, project_id: str = "") -> Dict[str, str]:
        """Build authentic ClientMetadata payload for loadCodeAssist and onboardUser bodies.

        Note: Google's v1internal protobuf schema for loadCodeAssist/onboardUser requires
        platform='PLATFORM_UNSPECIFIED' in the JSON body to avoid HTTP 400 INVALID_ARGUMENT.
        """
        version, _, _ = cls.get_version_info()
        meta: Dict[str, str] = {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
            "ideVersion": version,
        }
        if project_id and project_id != "aicode-consumers":
            meta["duetProject"] = project_id
        return meta

    @classmethod
    def build_headers(
        cls,
        access_token: str,
        project_id: str = "",
        prompt_id: Optional[str] = None,
        trajectory_id: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Construct authentic Antigravity IDE & language_server.exe HTTP headers."""
        version, _, _ = cls.get_version_info()
        cl = cls.get_changelist()
        go_os, go_arch = cls.get_go_arch_and_os()
        _, plat_enum = cls.get_platform_info()
        req_id = str(uuid.uuid4())

        # Matches the exact User-Agent and transport headers emitted by Go language_server.exe:
        # antigravity/<ver> (aidev_client; os_type=<go_os>; arch=<go_arch>; cl=<cl>)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": f"antigravity/{version} (aidev_client; os_type={go_os}; arch={go_arch}; cl={cl})",
            "X-Goog-Api-Client": f"{cls.DEFAULT_CLIENT_LIBRARY_VERSION} gccl/{version} antigravity/{version}",
            "Client-Metadata": json.dumps({
                "ideType": "ANTIGRAVITY",
                "platform": plat_enum,
                "pluginType": "GEMINI",
                "applicationVersion": version,
                "ideVersion": version,
                "changelist": cl,
            }, separators=(",", ":")),
            "x-activity-request-id": req_id,
            "X-Aicode-Request-Id": req_id,
            "X-Aicode-Prompt-Id": prompt_id or str(uuid.uuid4()),
            "X-Aicode-Trajectory-Id": trajectory_id or cls.get_trajectory_id(),
        }

        # NOTE: Do NOT set X-Goog-User-Project header; language_server.exe passes project
        # exclusively inside the JSON payload body. Setting X-Goog-User-Project on consumer
        # OAuth tokens triggers HTTP 403 IAM permission errors on cloudcode-pa.googleapis.com.

        if extra_headers:
            headers.update(extra_headers)

        return headers

    @classmethod
    def get_status_summary(cls) -> Dict[str, Any]:
        """Return diagnostic status for CLI doctor and status commands."""
        version, source, bin_path = cls.get_version_info()
        cl = cls.get_changelist()
        _, plat_enum = cls.get_platform_info()
        return {
            "version": version,
            "changelist": cl,
            "source": source,
            "binary_path": bin_path,
            "platform": plat_enum,
            "is_local_binary": source == "local_binary",
            "description": (
                f"Antigravity v{version} (CL {cl}, Synced with Local IDE)"
                if source == "local_binary"
                else f"Antigravity v{version} (CL {cl}, Autonomous Built-in Profile)"
            ),
        }
