# modules/verify.py
"""
Content-verification layer for OSINT hits.
Re-fetches entity URLs to validate Sherlock/Maigret results and
reduce false positives. Routes JS-heavy platforms to the headless
browser module.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import re
import httpx
from core.target_model import Entity

# Import headless probe's platform set for routing
try:
    from modules.headless_probe import JS_HEAVY_PLATFORMS, probe as headless_probe
except ImportError:
    JS_HEAVY_PLATFORMS = set()
    headless_probe = None


# ── Not-found signals (case-insensitive) ──────────────────────
_NOT_FOUND_STRINGS = [
    "doesn't exist",
    "does not exist",
    "user not found",
    "page not found",
    "this account doesn't exist",
    "this account does not exist",
    "sorry, this page",
    "this page isn't available",
    "content isn't available",
    "no results found",
    "couldn't find this account",
    "the page you were looking for",
    "hmm...this page doesn't exist",
    "nothing to see here",
    "account suspended",
    "profile isn't available",
    "the link may be broken",
    "profile may have been removed",
]

_NOT_FOUND_RE = re.compile(
    "|".join(re.escape(s) for s in _NOT_FOUND_STRINGS),
    re.IGNORECASE,
)

# Generic site titles that don't confirm a real profile
_GENERIC_TITLES = {
    "instagram", "tiktok", "facebook", "log in", "twitter",
    "snapchat", "linkedin", "x", "page not found", "404",
    "error", "not found", "reddit", "threads",
}

# Realistic browser User-Agent
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def verify_hit(entity: Entity, lessons_store=None, case_slug: str = None) -> Entity:
    """
    Verify that an entity's URL actually points to a real profile.
    Modifies entity.confidence and entity.metadata["verified"] in place.

    Args:
        entity:        The Entity to verify (must have metadata["url"]).
        lessons_store: Optional LessonsStore instance for RAG-based
                       prior confidence adjustment.
        case_slug:     The slug name of the active case folder.

    Returns:
        The same entity, with updated confidence and verified flag.
    """
    # ── Fix 2: API-confirmed targets should bypass verification checks ──
    api_confirmed_sources = {"github", "github_commits"}
    if any(src in api_confirmed_sources for src in entity.sources):
        entity.metadata["verified"] = True
        # Capture screenshot for API confirmed source if a URL and case_slug exist
        url = entity.metadata.get("url", "")
        if url and case_slug:
            try:
                import modules.evidence as evidence
                entity_id = f"{entity.entity_type}_{entity.value}_{entity.platform or 'api'}"
                entity_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", entity_id.lower())
                cap_res = await evidence.capture(url, case_slug, entity_id)
                if cap_res.get("success"):
                    entity.metadata["screenshot_path"] = cap_res.get("screenshot_path")
            except Exception:
                pass
        return entity

    url = entity.metadata.get("url", "")
    if not url:
        # No URL to verify — leave as-is
        return entity

    platform = (entity.platform or "").strip()

    # ── RAG prior: check past lessons before even fetching ─────
    if lessons_store and platform:
        try:
            warning = lessons_store.has_platform_warning(platform)
            if warning:
                # Past lesson says this platform is unreliable
                entity.confidence *= 0.5
                entity.metadata["lesson_warning"] = warning
        except Exception:
            pass  # Lessons store failure is non-fatal

    # ── Route: JS-heavy platforms → headless probe ─────────────
    # Make check case-insensitive to ensure matches like "Instagram" align with JS_HEAVY_PLATFORMS
    if platform.lower() in JS_HEAVY_PLATFORMS and headless_probe is not None:
        print(f"[verify] Routing '{platform}' via headless_probe for '{entity.value}'")
        return await _verify_via_headless(entity, url, platform, case_slug)

    # ── Route: standard HTTP verification ──────────────────────
    print(f"[verify] Routing '{platform}' via standard httpx fetch for '{entity.value}'")
    entity = await _verify_via_http(entity, url, platform)
    
    # ── Capture screenshot if verified and case_slug provided ──
    if entity.metadata.get("verified") is True and case_slug:
        try:
            import modules.evidence as evidence
            entity_id = f"{entity.entity_type}_{entity.value}_{platform.lower()}"
            entity_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", entity_id)
            cap_res = await evidence.capture(url, case_slug, entity_id)
            if cap_res.get("success"):
                entity.metadata["screenshot_path"] = cap_res.get("screenshot_path")
        except Exception:
            pass

    return entity


async def _verify_via_headless(entity: Entity, url: str, platform: str, case_slug: str = None) -> Entity:
    """Verify via Playwright headless browser."""
    try:
        entity_id = f"{entity.entity_type}_{entity.value}_{platform.lower()}"
        entity_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", entity_id)
        if case_slug:
            evidence_dir = Path(__file__).parent.parent / "cases" / case_slug / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(evidence_dir / f"{entity_id}.png")
        else:
            screenshot_path = None

        result = await headless_probe(url, platform, screenshot_path=screenshot_path)

        if result["exists"]:
            entity.metadata["verified"] = True
            entity.metadata["page_title"] = result.get("title", "")
            if result.get("og_description"):
                entity.metadata["description"] = result.get("og_description")
            if screenshot_path:
                entity.metadata["screenshot_path"] = f"cases/{case_slug}/evidence/{entity_id}.png"
        else:
            entity.metadata["verified"] = False
            entity.confidence *= 0.3
            if screenshot_path:
                try:
                    Path(screenshot_path).unlink(missing_ok=True)
                except Exception:
                    pass

    except Exception:
        # Headless probe crashed — inconclusive
        entity.metadata["verified"] = None
        entity.confidence *= 0.6

    return entity


async def _verify_via_http(entity: Entity, url: str, platform: str) -> Entity:
    """Verify via direct HTTP fetch + HTML content analysis."""
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            r = await client.get(url)

            # Hard 404/410 — clear signal
            if r.status_code in (404, 410):
                entity.metadata["verified"] = False
                entity.confidence *= 0.2
                return entity

            # Non-200 — inconclusive
            if r.status_code != 200:
                entity.metadata["verified"] = None
                entity.confidence *= 0.6
                return entity

            html = r.text[:10000]  # First 10KB is enough
            html_lower = html.lower()

            # Check for not-found signals in body
            has_not_found = bool(_NOT_FOUND_RE.search(html_lower))

            # Check for positive profile signals
            has_og_title = 'property="og:title"' in html_lower or "property='og:title'" in html_lower
            has_og_image = 'property="og:image"' in html_lower or "property='og:image'" in html_lower

            # Extract <title> for generic check
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            page_title = title_match.group(1).strip() if title_match else ""
            is_generic_title = page_title.lower().strip() in _GENERIC_TITLES

            has_profile_signal = (
                (has_og_title or has_og_image)
                and not is_generic_title
            )

            # Extract og:description
            desc_match = re.search(r'property=["\']og:description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
            if not desc_match:
                desc_match = re.search(r'content=["\'](.*?)["\']\s+property=["\']og:description["\']', html, re.IGNORECASE)
            og_desc = desc_match.group(1).strip() if desc_match else ""

            if has_not_found:
                entity.metadata["verified"] = False
                entity.confidence *= 0.3
            elif has_profile_signal:
                entity.metadata["verified"] = True
                entity.metadata["page_title"] = page_title
                if og_desc:
                    entity.metadata["description"] = og_desc
            elif not is_generic_title and page_title:
                # Has a non-generic title but no og tags — cautiously accept
                entity.metadata["verified"] = True
                entity.metadata["page_title"] = page_title
                if og_desc:
                    entity.metadata["description"] = og_desc
            else:
                # Inconclusive — no clear signals either way
                entity.metadata["verified"] = None
                entity.confidence *= 0.6

    except httpx.TimeoutException:
        # Timeout — inconclusive, don't penalize too hard
        entity.metadata["verified"] = None
        entity.confidence *= 0.7

    except Exception:
        # Any other fetch error — inconclusive
        entity.metadata["verified"] = None
        entity.confidence *= 0.6

    return entity
