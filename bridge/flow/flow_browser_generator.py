"""Flow Browser Generator — Autonomous browser-driven video generator for flow.google.com.

Allows Hermes to generate videos directly via the persistent browser session
without requiring manual browser clicks or external OAuth token refresh.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("tools.antigravity_bridge.flow.browser_generator")


class FlowBrowserGenerator:
    """Automates video creation and downloading on flow.google.com."""

    def __init__(self, profile_dir: Optional[Path] = None):
        self.profile_dir = profile_dir or (Path.home() / ".hermes" / "flow_browser_session")

    def generate_video_sync(
        self,
        prompt: str,
        output_path: Path,
        duration: int = 4,
        timeout: int = 180,
    ) -> Tuple[bool, str]:
        """Synchronous wrapper to generate and download video."""
        from playwright.sync_api import sync_playwright

        if not self.profile_dir.is_dir():
            return False, f"Browser profile dir does not exist: {self.profile_dir}"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        try:
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel="chrome",
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                # Step 1: Navigate to Google Flow
                logger.info("[FlowBrowser] Navigating to flow.google.com...")
                page.goto("https://flow.google.com/", timeout=45000)
                page.wait_for_timeout(3000)

                # Dismiss welcome/changelog modal if present
                btn_start = page.get_by_text("Get started")
                if btn_start.count() > 0:
                    btn_start.first.click()
                    page.wait_for_timeout(1500)

                # Step 2: Ensure inside a project or open existing project
                if "/project/" not in page.url:
                    new_proj = page.get_by_text("New project")
                    if new_proj.count() > 0:
                        new_proj.first.click()
                        page.wait_for_timeout(4000)

                # Dismiss project modal if present
                btn_start = page.get_by_text("Get started")
                if btn_start.count() > 0:
                    btn_start.first.click()
                    page.wait_for_timeout(1500)

                # Step 3: Enter prompt
                input_el = page.locator("textarea, [contenteditable='true']").first
                if input_el.count() == 0:
                    ctx.close()
                    return False, "Could not locate prompt input on flow.google.com"

                logger.info("[FlowBrowser] Typing prompt: %s", prompt[:60])
                input_el.click()
                input_el.fill(prompt)
                page.wait_for_timeout(800)

                # Step 4: Click 'Start generation'
                gen_btn = page.locator("button[aria-label='Start generation']")
                if gen_btn.count() > 0:
                    gen_btn.first.click()
                    logger.info("[FlowBrowser] Clicked Start generation.")
                else:
                    page.keyboard.press("Enter")

                page.wait_for_timeout(3000)

                # Step 5: Check for confirmation (Approve / Always approve)
                always_approve = page.get_by_text("Always approve")
                if always_approve.count() > 0:
                    always_approve.first.click()
                    logger.info("[FlowBrowser] Clicked Always approve.")
                else:
                    approve = page.get_by_text("Approve")
                    if approve.count() > 0:
                        approve.first.click()
                        logger.info("[FlowBrowser] Clicked Approve.")

                # Step 6: Wait for generation to complete (stop button disappears or media card renders)
                logger.info("[FlowBrowser] Waiting for video rendering to finish...")
                card_ready = False
                while time.time() - start_time < timeout:
                    stop_btn = page.locator("button:has-text('Stop'), button[aria-label*='Stop']")
                    has_img = page.locator("img[src*='flow-content.google']").count() > 0

                    if not stop_btn.count() and has_img:
                        card_ready = True
                        break

                    page.wait_for_timeout(4000)

                if not card_ready:
                    ctx.close()
                    return False, "Timed out waiting for video generation to complete."

                logger.info("[FlowBrowser] Generation completed! Opening media details...")
                target_img = page.locator("img[src*='flow-content.google']").first
                if target_img.count() > 0:
                    target_img.click()
                    page.wait_for_timeout(2000)

                # Step 7: Trigger Download -> 720p Original size
                dl_btn = page.locator("button[aria-label='Download media']")
                if dl_btn.count() == 0:
                    ctx.close()
                    return False, "Download media button not found on video details."

                dl_btn.first.click()
                page.wait_for_timeout(1000)

                item_720 = page.locator("[role='menuitem']:has-text('720p'), .mat-mdc-menu-item:has-text('720p')").first
                if item_720.count() == 0:
                    ctx.close()
                    return False, "720p download option not found in menu."

                logger.info("[FlowBrowser] Downloading 720p video file...")
                with page.expect_download(timeout=30000) as download_info:
                    item_720.click()
                download = download_info.value
                download.save_as(str(output_path))

                ctx.close()
                if output_path.is_file() and output_path.stat().st_size > 1000:
                    logger.info("[FlowBrowser] Successfully downloaded video to %s (%d bytes)", output_path, output_path.stat().st_size)
                    return True, str(output_path.resolve())
                return False, "Downloaded file is empty or missing."

        except Exception as exc:
            logger.exception("[FlowBrowser] Error during browser generation: %s", exc)
            return False, f"Browser generation error: {exc}"
