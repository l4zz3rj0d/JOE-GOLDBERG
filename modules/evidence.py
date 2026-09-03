# modules/evidence.py
"""
Evidence capture module.
Takes full-page screenshots of verified targets and saves them.
"""
import sys
from pathlib import Path
from datetime import datetime
import asyncio

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


async def capture(url: str, case_slug: str, entity_id: str) -> dict:
    """
    Capture a full-page screenshot of a URL.
    Uses the browser context setup from modules/headless_probe.py.

    Returns:
        {"screenshot_path": str|None, "captured_at": str, "success": bool}
    """
    result = {
        "screenshot_path": None,
        "captured_at": datetime.now().isoformat(),
        "success": False
    }

    try:
        from playwright.async_api import async_playwright
        from modules.headless_probe import get_browser_context
    except Exception:
        # Playwright not available — degrade silently
        return result

    browser = None
    try:
        evidence_dir = PROJECT_ROOT / "cases" / case_slug / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(evidence_dir / f"{entity_id}.png")

        async with async_playwright() as pw:
            try:
                browser, context = await get_browser_context(pw)
                page = await context.new_page()

                try:
                    await page.goto(url, wait_until="networkidle", timeout=10000)
                except Exception:
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=6000)
                    except Exception:
                        return result

                # Extra settle time
                await asyncio.sleep(1.0)

                # Capture screenshot
                await page.screenshot(path=screenshot_path, full_page=True)
                await context.close()

                result["screenshot_path"] = f"cases/{case_slug}/evidence/{entity_id}.png"
                result["success"] = True
            except Exception:
                pass

    except Exception:
        # Graceful degradation: handle silently
        pass
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

    return result

