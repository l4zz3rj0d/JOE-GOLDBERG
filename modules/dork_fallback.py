# modules/dork_fallback.py
"""
Dork Fallback Module.
Performs Google searches when primary OSINT tools return zero results.
"""
import sys
from pathlib import Path
import asyncio
import re
import time
import httpx
import urllib.parse
from core.target_model import Entity, Target

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Global tracking to ensure fallback only runs once per module per target
_triggered_dorks = set()

# Rate-limiting state — prevent rapid-fire dork calls that trigger Google soft-blocks
_MIN_DORK_INTERVAL = 3.5  # seconds between consecutive dork requests
_last_dork_time = 0.0


async def dork(target: Target, query: str, site_filter: str, entity_type: str, on_find=None, module_name: str = "") -> tuple[int, str]:
    """
    Perform a dork fallback search against Google.
    Returns:
        A tuple of (number of new entities added, status_string).
        status_string can be "success", "empty", "blocked", or "skipped".
    """
    key = (target.primary, module_name)
    if key in _triggered_dorks:
        return 0, "skipped"
    _triggered_dorks.add(key)

    # Enforce minimum interval between consecutive dork calls
    global _last_dork_time
    now = time.monotonic()
    elapsed = now - _last_dork_time
    if _last_dork_time > 0 and elapsed < _MIN_DORK_INTERVAL:
        delay = _MIN_DORK_INTERVAL - elapsed
        target.log("dork_rate_limited_delay", {
            "delay_seconds": round(delay, 2),
            "query": query,
            "module": module_name
        })
        await asyncio.sleep(delay)
    _last_dork_time = time.monotonic()

    count = 0
    status = "empty"
    try:
        q = f"site:{site_filter} {query}" if site_filter else query
        async with httpx.AsyncClient(
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                )
            }
        ) as client:
            r = await client.get(f"https://www.google.com/search?q={urllib.parse.quote(q)}")
            
            # Check for rate-limiting, CAPTCHA redirect or blocks
            blocked = False
            if r.status_code in (403, 429, 503):
                blocked = True
            elif "google.com/sorry/" in r.text or "unusual traffic" in r.text.lower() or "captcha" in r.text.lower():
                blocked = True
                
            if blocked:
                target.log("google_dork_blocked", {"query": query, "module": module_name})
                return 0, "blocked"

            if r.status_code == 200:
                # Find redirects (e.g. /url?q=...)
                urls = re.findall(r'/url\?q=(https?://[^\s&"]+)', r.text)

                # Soft-block detection: 200 response but suspiciously empty
                # Real "no results" pages from Google are still several KB;
                # a scraped-away soft-block is typically very short with no result URLs
                if not urls and len(r.text) < 1500:
                    target.log("google_dork_blocked", {
                        "query": query,
                        "module": module_name,
                        "reason": "soft_block_empty_200"
                    })
                    return 0, "blocked"

                seen = set()
                for raw_url in urls:
                    decoded_url = urllib.parse.unquote(raw_url)
                    
                    # Clean/filter urls
                    if "google.com" in decoded_url.lower():
                        continue
                    
                    if site_filter and site_filter.lower() not in decoded_url.lower():
                        continue

                    if decoded_url not in seen:
                        seen.add(decoded_url)

                        netloc = urllib.parse.urlparse(decoded_url).netloc
                        platform = netloc.replace("www.", "").capitalize()

                        entity = Entity(
                            entity_type=entity_type,
                            value=decoded_url,
                            sources=["google_dork_fallback"],
                            confidence=0.6,
                            platform=platform,
                            metadata={
                                "url": decoded_url,
                                "query": query,
                                "site_filter": site_filter,
                                "verified": None,
                            }
                        )

                        if target.add_entity(entity):
                            count += 1
                            if on_find:
                                await on_find(entity)

                        if count >= 5:
                            break
    except Exception:
        pass

    if count > 0:
        status = "success"
        target.log("google_dork_success", {"query": query, "module": module_name, "found": count})
    else:
        status = "empty"
        target.log("google_dork_empty", {"query": query, "module": module_name})

    return count, status
