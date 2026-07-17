# modules/headless_probe.py
"""
Headless browser probe for JS-heavy platforms.
Uses Playwright (Chromium) to render pages that httpx can't verify.
Degrades gracefully if Playwright is not installed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import re

# Platforms known to require JS rendering for profile verification
JS_HEAVY_PLATFORMS = {
    "instagram", "tiktok", "facebook", "twitter", "x",
    "threads", "snapchat", "linkedin",
}

# Signals that indicate a profile does NOT exist
_NOT_FOUND_PATTERNS = [
    r"page not found",
    r"user not found",
    r"this account doesn't exist",
    r"doesn't exist",
    r"sorry, this page",
    r"content isn't available",
    r"this page isn't available",
    r"no results found",
    r"404",
    r"couldn't find this account",
    r"profile isn't available",
    r"the link may be broken",
    r"profile may have been removed",
]

_NOT_FOUND_RE = re.compile(
    "|".join(_NOT_FOUND_PATTERNS), re.IGNORECASE
)


async def get_browser_context(pw):
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return browser, context


async def probe(url: str, platform: str, screenshot_path: str|None = None) -> dict:
    """
    Load a URL in headless Chromium, wait for JS rendering, check
    whether a real profile exists, and optionally capture a screenshot.

    Returns:
        {"exists": bool, "title": str, "og_image": str|None}
    """
    result = {"exists": False, "title": "", "og_image": None}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # Playwright not installed — degrade silently
        return result

    browser = None
    try:
        async with async_playwright() as pw:
            browser, context = await get_browser_context(pw)
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=12000)
            except Exception:
                # Timeout or navigation error — try domcontentloaded fallback
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=8000)
                except Exception:
                    return result

            # Extra settle time for late-rendering SPAs
            await asyncio.sleep(1.5)

            # Extract title
            title = await page.title() or ""
            result["title"] = title.strip()

            # Extract og:image
            og_image = await page.evaluate("""
                () => {
                    const el = document.querySelector('meta[property="og:image"]');
                    return el ? el.getAttribute('content') : null;
                }
            """)
            result["og_image"] = og_image

            # Extract og:description
            og_desc = await page.evaluate("""
                () => {
                    const el = document.querySelector('meta[property="og:description"]') || document.querySelector('meta[name="description"]');
                    return el ? el.getAttribute('content') : null;
                }
            """)
            result["og_description"] = og_desc

            # Extract og:title for additional signal
            og_title = await page.evaluate("""
                () => {
                    const el = document.querySelector('meta[property="og:title"]');
                    return el ? el.getAttribute('content') : null;
                }
            """)

            # Get visible text for not-found detection
            body_text = await page.evaluate("""
                () => document.body ? document.body.innerText.substring(0, 3000) : ''
            """)

            # Decision logic
            has_not_found = bool(_NOT_FOUND_RE.search(body_text or ""))
            has_not_found_title = bool(_NOT_FOUND_RE.search(title))

            # Generic titles that don't confirm a real profile
            platform_lower = platform.lower()
            generic_titles = {
                "instagram": ["instagram"],
                "tiktok": ["tiktok", "make your day"],
                "facebook": ["facebook", "log in", "log into facebook"],
                "twitter": ["x", "twitter"],
                "x": ["x", "twitter"],
                "threads": ["threads"],
                "snapchat": ["snapchat"],
                "linkedin": ["linkedin"],
            }
            is_generic_title = False
            for gt in generic_titles.get(platform_lower, []):
                if title.lower().strip() == gt.lower().strip():
                    is_generic_title = True
                    break

            has_profile_signal = (
                (og_title and not _NOT_FOUND_RE.search(og_title))
                or (og_image and "default" not in og_image.lower())
                or (title and not is_generic_title and not has_not_found_title)
            )

            if has_not_found:
                result["exists"] = False
            elif has_profile_signal:
                result["exists"] = True
                if screenshot_path:
                    try:
                        Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                        await page.screenshot(path=screenshot_path, full_page=True)
                    except Exception:
                        pass
            else:
                # Inconclusive — lean towards not existing
                result["exists"] = False

            await context.close()

    except Exception:
        # Any Playwright crash — degrade silently
        pass
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

    return result
