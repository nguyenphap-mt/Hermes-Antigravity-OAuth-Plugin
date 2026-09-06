"""Bridge between Antigravity OAuth tokens and Google Flow browser sessions.

Converts OAuth access tokens into browser cookies so Playwright can
authenticate to Google Flow without a manual login prompt.
"""

import json
import logging
import time
from typing import Optional

try:
    from playwright.async_api import BrowserContext, Page
except ImportError:
    BrowserContext = object  # type: ignore
    Page = object  # type: ignore

logger = logging.getLogger(__name__)

# Google domains that need auth cookies
GOOGLE_COOKIE_DOMAINS = [
    ".google.com",
    ".labs.google",
    "labs.google",
    ".accounts.google.com",
]

# Cookie names used by Google for authentication
GOOGLE_AUTH_COOKIES = [
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "NID", "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
]


async def inject_oauth_session(
    context: BrowserContext,
    access_token: str,
    email: str = "",
) -> bool:
    """Inject OAuth access token into browser context for Google Flow auth.

    Strategy:
    1. Navigate to Google's OAuth token info endpoint to validate token
    2. Use the token to establish a session via Google's auth redirect
    3. Store resulting cookies in the browser context

    Args:
        context: Playwright browser context
        access_token: Valid Google OAuth access token
        email: Optional email for cookie identification

    Returns:
        True if session was established successfully
    """
    page = await context.new_page()
    try:
        # Step 1: Use OAuth token to authenticate via Google's endpoint
        # Navigate to a Google property that accepts Bearer tokens
        auth_url = (
            "https://accounts.google.com/o/oauth2/auth?"
            "response_type=none"
            f"&access_token={access_token}"
            "&redirect_uri=https://labs.google/fx/tools/flow"
            "&client_id=1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
            "&scope=openid email profile"
        )

        # Step 2: Try direct token-based auth via userinfo endpoint
        # This establishes the session cookies
        logger.info("Establishing Google session via OAuth token...")

        # First, validate the token and get user info
        userinfo_page = await context.new_page()
        try:
            await userinfo_page.goto(
                f"https://www.googleapis.com/oauth2/v1/userinfo?access_token={access_token}",
                timeout=15000,
            )
            content = await userinfo_page.text_content("pre")
            if content:
                user_data = json.loads(content)
                detected_email = user_data.get("email", email)
                logger.info("OAuth token valid for: %s", detected_email)
        except Exception as e:
            logger.warning("Token validation via userinfo failed: %s", e)
        finally:
            await userinfo_page.close()

        # Step 3: Navigate to Google Flow with token in Authorization header
        # Use route interception to inject the Bearer token
        async def inject_auth_header(route, request):
            headers = {**request.headers, "Authorization": f"Bearer {access_token}"}
            await route.continue_(headers=headers)

        await page.route("https://labs.google/**", inject_auth_header)
        await page.route("https://accounts.google.com/**", inject_auth_header)

        # Navigate to Flow — this should trigger Google's auth flow
        response = await page.goto(
            "https://labs.google/fx/tools/flow",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # Step 4: Check if we're authenticated
        await page.wait_for_timeout(3000)  # Wait for JS hydration

        is_logged_in = await verify_login(page)
        if is_logged_in:
            logger.info("Successfully authenticated to Google Flow")
            return True

        # Step 5: Fallback — try cookie-based auth
        logger.info("Direct auth failed, trying cookie injection fallback...")
        return await _fallback_cookie_auth(context, page, access_token)

    except Exception as e:
        logger.error("Failed to establish Google Flow session: %s", e)
        return False
    finally:
        await page.close()


async def _fallback_cookie_auth(
    context: BrowserContext,
    page: Page,
    access_token: str,
) -> bool:
    """Fallback: Set minimal cookies to enable Google Flow access.

    This attempts to set cookies that Google Flow checks for auth state.
    May not work if Google requires full session cookies.
    """
    timestamp = int(time.time())

    # Set a basic auth cookie structure
    cookies_to_set = [
        {
            "name": "oauth_token",
            "value": access_token,
            "domain": ".labs.google",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
            "expires": timestamp + 3600,
        },
        {
            "name": "access_token",
            "value": access_token,
            "domain": ".labs.google",
            "path": "/fx/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
            "expires": timestamp + 3600,
        },
    ]

    try:
        await context.add_cookies(cookies_to_set)
        await page.reload(wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
        return await verify_login(page)
    except Exception as e:
        logger.warning("Fallback cookie auth failed: %s", e)
        return False


async def verify_login(page: Page) -> bool:
    """Verify if the current browser session is logged in to Google Flow."""
    try:
        # Check for user avatar (indicates logged in)
        avatar = await page.query_selector(
            'img[alt*="Google Account"], '
            'button[aria-label*="Google Account"], '
            '[data-ogsr-up], '
            'a[aria-label*="Google Account"]'
        )
        if avatar:
            return True

        # Check for sign-in button (indicates NOT logged in)
        sign_in = await page.query_selector(
            'a:has-text("Sign in"), '
            'button:has-text("Sign in"), '
            'a[href*="accounts.google.com/ServiceLogin"]'
        )
        if sign_in:
            return False

        # Check page URL — if redirected to accounts.google.com, not logged in
        url = getattr(page, "url", "") or ""
        if "accounts.google.com" in url:
            return False

        # If we're on a Flow page without sign-in prompt, assume logged in
        if "labs.google/fx" in url:
            return True

        return False
    except Exception:
        return False


async def extract_session_cookies(context: BrowserContext) -> list:
    """Extract all Google-related cookies from the browser context.

    Useful for persisting the session across restarts.
    """
    all_cookies = await context.cookies()
    google_cookies = [
        c for c in all_cookies
        if any(domain in c.get("domain", "") for domain in [".google.com", ".labs.google"])
    ]
    return google_cookies


async def restore_session_cookies(context: BrowserContext, cookies: list) -> None:
    """Restore previously saved Google session cookies into a browser context."""
    if cookies:
        await context.add_cookies(cookies)
        logger.info("Restored %d Google session cookies", len(cookies))
