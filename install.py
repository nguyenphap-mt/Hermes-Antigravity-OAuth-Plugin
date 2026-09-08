#!/usr/bin/env python3
"""1-Click Standalone & Multi-Workspace Installer for Hermes Antigravity OAuth Plugin.

Features:
- Multi-Home Discovery: Installs into ~/.hermes, AppData/Local/hermes, and all user profiles.
- Multi-Workspace Discovery: Syncs with all detected hermes-agent git repositories.
- Cache Invalidation: Wipes stale provider_models_cache.json so dynamic models load immediately.
- Update-Proof: Keeps plugin and bridge files persistent across Hermes core updates.

Usage:
  python install.py
"""

import os
import sys
import shutil
from pathlib import Path
from typing import List, Set

PACKAGE_DIR = Path(__file__).resolve().parent

def get_candidate_hermes_homes() -> List[Path]:
    """Find all Hermes home directories and profile directories on the system."""
    homes: Set[Path] = set()

    # 1. HERMES_HOME env var
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        try:
            homes.add(Path(env_home).expanduser().resolve())
        except Exception:
            pass

    # 2. Standard ~/.hermes
    dot_hermes = (Path.home() / ".hermes").resolve()
    homes.add(dot_hermes)

    # 3. Windows AppData / Local / hermes
    if sys.platform == "win32":
        appdata_hermes = (Path.home() / "AppData" / "Local" / "hermes").resolve()
        if appdata_hermes.exists():
            homes.add(appdata_hermes)

    # 4. Scan profiles under all found homes
    profile_dirs: Set[Path] = set()
    for h in list(homes):
        profiles_root = h / "profiles"
        if profiles_root.is_dir():
            for p in profiles_root.iterdir():
                if p.is_dir() and not p.name.startswith("."):
                    profile_dirs.add(p.resolve())

    all_homes = list(homes) + list(profile_dirs)
    return [h for h in all_homes if h.exists() or h == dot_hermes]


def get_candidate_workspaces() -> List[Path]:
    """Find all local hermes-agent git checkouts on the machine."""
    candidates: Set[Path] = set()

    # Current parent
    p = PACKAGE_DIR.parent
    if (p / "run_agent.py").is_file() and (p / "hermes_cli").is_dir():
        candidates.add(p.resolve())

    # User home checkouts
    home = Path.home()
    common_names = ["hermes-agent", "hermes-agent-sqlite-staging", "hermes", "hermes-core"]
    for name in common_names:
        candidate = home / name
        if (candidate / "run_agent.py").is_file() and (candidate / "hermes_cli").is_dir():
            candidates.add(candidate.resolve())

    return list(candidates)


def invalidate_stale_caches(homes: List[Path]):
    """Clean all stale provider_models_cache.json across all discovered homes."""
    for h in homes:
        for p in h.rglob("*models_cache*.json"):
            try:
                p.unlink()
            except Exception:
                pass


def main():
    print("=" * 68)
    print("   HERMES AGENT - GOOGLE ANTIGRAVITY OAUTH PLUGIN INSTALLER   ")
    print("=" * 68)

    plugin_src = PACKAGE_DIR / "plugin"
    bridge_src = PACKAGE_DIR / "bridge"
    image_gen_src = PACKAGE_DIR / "image_gen" / "antigravity"
    video_gen_src = PACKAGE_DIR / "video_gen" / "antigravity"
    dashboard_src = PACKAGE_DIR / "dashboard"
    tests_src = PACKAGE_DIR / "tests"

    homes = get_candidate_hermes_homes()
    print(f"\n[1/4] Discovered {len(homes)} Hermes environment(s) & profile(s):")
    for h in homes:
        print(f"      * {h}")

    # 1. Install to all discovered Hermes Homes & Profiles
    print("\n[2/4] Installing Plugin, Bridge Engine, Video/Image Providers & Dashboard...")
    for h in homes:
        h.mkdir(parents=True, exist_ok=True)

        # Model provider plugin
        plugin_dest = h / "plugins" / "model-providers" / "antigravity"
        plugin_dest.mkdir(parents=True, exist_ok=True)
        for f in plugin_src.glob("*"):
            if f.is_file():
                shutil.copy2(f, plugin_dest / f.name)

        # Bridge runtime engine
        bridge_dest = h / "bridge" / "antigravity" / "tools" / "antigravity_bridge"
        bridge_dest.parent.mkdir(parents=True, exist_ok=True)
        if bridge_dest.exists():
            shutil.rmtree(bridge_dest, ignore_errors=True)
        shutil.copytree(bridge_src, bridge_dest)

        # Manager CLI
        shutil.copy2(PACKAGE_DIR / "manage.py", h / "bridge" / "antigravity" / "manage.py")

        # Dashboard plugin (Update-proof in ~/.hermes/plugins/antigravity/dashboard)
        if dashboard_src.exists():
            dash_dest = h / "plugins" / "antigravity" / "dashboard"
            dash_dest.mkdir(parents=True, exist_ok=True)
            for f in dashboard_src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, dash_dest / f.name)
            dist_src = dashboard_src / "dist"
            if dist_src.is_dir():
                dist_dest = dash_dest / "dist"
                dist_dest.mkdir(parents=True, exist_ok=True)
                for f in dist_src.glob("*"):
                    if f.is_file():
                        shutil.copy2(f, dist_dest / f.name)

        # Image generation plugin
        if image_gen_src.exists():
            img_dest = h / "plugins" / "image_gen" / "antigravity"
            img_dest.mkdir(parents=True, exist_ok=True)
            for f in image_gen_src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, img_dest / f.name)

        # Video generation plugin (Google Flow Veo AI)
        if video_gen_src.exists():
            vgen_dest = h / "plugins" / "video_gen" / "antigravity"
            vgen_dest.mkdir(parents=True, exist_ok=True)
            for f in video_gen_src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, vgen_dest / f.name)

        # AI Video Generation skill (Google Flow Veo 3.1 & Omni)
        skill_src = PACKAGE_DIR / "skills" / "ai-video-generation"
        if skill_src.exists():
            h_skill = h / "skills" / "ai-video-generation"
            h_skill.mkdir(parents=True, exist_ok=True)
            for sf in skill_src.glob("*"):
                if sf.is_file():
                    shutil.copy2(sf, h_skill / sf.name)

        # Configure config.yaml
        # NOTE: video_gen is ONLY activated on the main profile (hermes-main / root homes)
        is_main_profile = "profiles" not in h.parts
        cfg_file = h / "config.yaml"
        if cfg_file.exists():
            try:
                import yaml
                with open(cfg_file, "r", encoding="utf-8") as fp:
                    data = yaml.safe_load(fp) or {}
                if isinstance(data, dict):
                    data.setdefault("image_gen", {})["provider"] = "antigravity"
                    plugs = data.setdefault("plugins", {})
                    enabled_list = plugs.setdefault("enabled", [])
                    if "image_gen/antigravity" not in enabled_list:
                        enabled_list.append("image_gen/antigravity")
                    if "antigravity" not in enabled_list:
                        enabled_list.append("antigravity")

                    if is_main_profile:
                        # Activate video_gen exclusively on main profile
                        data.setdefault("video_gen", {})["provider"] = "antigravity"
                        # Preserve existing configured model or default to omni-1.1-flash
                        vgen_cfg = data.setdefault("video_gen", {})
                        if not vgen_cfg.get("model") or vgen_cfg.get("model") == "veo-2-10s":
                            vgen_cfg["model"] = "omni-1.1-flash"
                        if "video_gen/antigravity" not in enabled_list:
                            enabled_list.append("video_gen/antigravity")

                    with open(cfg_file, "w", encoding="utf-8") as fp:
                        yaml.dump(data, fp, default_flow_style=False)
            except Exception:
                pass

    print("      + Successfully installed & configured across all homes and profiles.")

    # 2. In-Repo synchronization across all checkouts
    workspaces = get_candidate_workspaces()
    print(f"\n[3/4] Discovered {len(workspaces)} active hermes-agent workspace(s):")
    for ws in workspaces:
        print(f"      * {ws}")
        ws_plugin = ws / "plugins" / "model-providers" / "antigravity"
        ws_tools = ws / "tools" / "antigravity_bridge"
        ws_img = ws / "plugins" / "image_gen" / "antigravity"
        ws_vgen = ws / "plugins" / "video_gen" / "antigravity"
        ws_dash = ws / "plugins" / "antigravity" / "dashboard"
        ws_tests = ws / "tests" / "tools"

        ws_plugin.mkdir(parents=True, exist_ok=True)
        for f in plugin_src.glob("*"):
            if f.is_file():
                shutil.copy2(f, ws_plugin / f.name)

        if ws_tools.exists():
            shutil.rmtree(ws_tools, ignore_errors=True)
        shutil.copytree(bridge_src, ws_tools)

        if dashboard_src.exists():
            ws_dash.mkdir(parents=True, exist_ok=True)
            for f in dashboard_src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, ws_dash / f.name)
            dist_src = dashboard_src / "dist"
            if dist_src.is_dir():
                dist_dest = ws_dash / "dist"
                dist_dest.mkdir(parents=True, exist_ok=True)
                for f in dist_src.glob("*"):
                    if f.is_file():
                        shutil.copy2(f, dist_dest / f.name)

        if image_gen_src.exists():
            ws_img.mkdir(parents=True, exist_ok=True)
            for f in image_gen_src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, ws_img / f.name)

        if video_gen_src.exists():
            ws_vgen.mkdir(parents=True, exist_ok=True)
            for f in video_gen_src.glob("*"):
                if f.is_file():
                    shutil.copy2(f, ws_vgen / f.name)

        if tests_src.exists():
            ws_tests.mkdir(parents=True, exist_ok=True)
            for test_file in tests_src.glob("test_*.py"):
                if test_file.is_file():
                    shutil.copy2(test_file, ws_tests / test_file.name)

        # Ensure video_generate is in _HERMES_CORE_TOOLS in toolsets.py
        ws_toolsets = ws / "toolsets.py"
        if ws_toolsets.is_file():
            ts_text = ws_toolsets.read_text(encoding="utf-8")
            if '"video_generate"' not in ts_text:
                ts_text = ts_text.replace('"image_generate",', '"image_generate", "video_generate",')
                ws_toolsets.write_text(ts_text, encoding="utf-8")

        # Copy ai-video-generation skill
        skill_src = PACKAGE_DIR / "skills" / "ai-video-generation"
        if skill_src.exists():
            ws_skill = ws / "skills" / "ai-video-generation"
            ws_skill.mkdir(parents=True, exist_ok=True)
            for sf in skill_src.glob("*"):
                if sf.is_file():
                    shutil.copy2(sf, ws_skill / sf.name)

    # 3. Install Git post-merge hooks for update resilience
    print("\n[4/5] Installing Git post-merge auto-resync hooks...")
    installer_path = (PACKAGE_DIR / "install.py").resolve()
    for ws in workspaces:
        hooks_dir = ws / ".git" / "hooks"
        if hooks_dir.is_dir():
            hook_file = hooks_dir / "post-merge"
            hook_content = (
                "#!/bin/sh\n"
                "# Hermes Antigravity & Google Flow Auto-Resync Hook\n"
                "# Triggered automatically after 'git pull' or 'git merge' to preserve plugins & config\n"
                f'python "{installer_path}"\n'
            )
            try:
                hook_file.write_text(hook_content, encoding="utf-8")
                try:
                    hook_file.chmod(0o755)
                except Exception:
                    pass
                print(f"      + Git post-merge hook installed in: {hook_file.parent.parent.name}")
            except Exception as e:
                print(f"      ! Failed to install hook in {ws}: {e}")

    # 4. Clear Stale Caches
    print("\n[5/5] Invalidating stale model caches...")
    invalidate_stale_caches(homes)
    print("      + Caches cleared. Fresh dynamic models will load immediately.")

    print("\n" + "=" * 68)
    print(" INSTALLATION & MULTI-WORKSPACE SYNC COMPLETED SUCCESSFULLY!")
    print("=" * 68)
    print("\nNext Steps:")
    print("  1. Check status & accounts: python manage.py status")
    print("  2. If gateway is running, restart it to load fresh code.")
    print("  3. On Telegram/CLI: Run /model to pick any of the 32 dynamic models.")
    print("=" * 68)

if __name__ == "__main__":
    main()
