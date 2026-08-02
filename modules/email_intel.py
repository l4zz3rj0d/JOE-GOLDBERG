# modules/email_intel.py
"""
Generalized Email Intelligence module.
Runs multi-technique email enrichment including Gravatar profile extraction,
Libravatar / WordPress hash-reuse checks, and Google Maps contributor targeted dorks.
"""
import sys
import hashlib
import asyncio
import re
from pathlib import Path
import httpx

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import Entity, Target

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def enrich(target: Target, email: str, on_find=None) -> None:
    """
    Run multi-technique email intelligence enrichment.
    Sub-checks run concurrently and degrade gracefully.
    """
    if not email or not isinstance(email, str):
        return

    clean_email = email.strip().lower()

    await asyncio.gather(
        _run_gravatar(target, clean_email, on_find),
        _run_libravatar_hash_check(target, clean_email, on_find),
        _run_google_maps_contrib_dork(target, clean_email, on_find),
        return_exceptions=True,
    )


async def _run_gravatar(target: Target, email: str, on_find=None) -> None:
    """1. Gravatar profile enrichment."""
    try:
        import modules.gravatar_profile as gravatar_profile
        await gravatar_profile.enrich(target, email, on_find)
    except Exception:
        pass


async def _run_libravatar_hash_check(target: Target, email: str, on_find=None) -> None:
    """2. Check MD5 email hash against Libravatar / federated avatar service."""
    try:
        email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()

        # Check if Libravatar avatar exists (returns 200 with default=404 parameter)
        libravatar_url = f"https://seventeen.libravatar.org/avatar/{email_hash}?d=404"
        async with httpx.AsyncClient(
            timeout=8,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            r = await client.get(libravatar_url)
            if r.status_code == 200 and r.content and len(r.content) > 100:
                evidence_dir = PROJECT_ROOT / "cases" / target.case_slug / "evidence"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                avatar_filename = f"libravatar_{email_hash}.png"
                avatar_file = evidence_dir / avatar_filename
                avatar_file.write_bytes(r.content)
                avatar_path = f"cases/{target.case_slug}/evidence/{avatar_filename}"

                entity = Entity(
                    entity_type="profile_link",
                    value=f"https://www.libravatar.org/avatar/{email_hash}",
                    sources=["libravatar"],
                    confidence=0.80,
                    platform="Libravatar",
                    metadata={
                        "email": email,
                        "email_hash": email_hash,
                        "url": f"https://www.libravatar.org/avatar/{email_hash}",
                        "avatar_path": avatar_path,
                        "verified": True,
                    },
                )
                if target.add_entity(entity) and on_find:
                    await on_find(entity)
    except Exception:
        pass


async def _run_google_maps_contrib_dork(target: Target, email: str, on_find=None) -> None:
    """
    3. Targeted Google Maps contributor page dork.
    Guardrail: Only run if Google account is confirmed and at least one name or username
    entity already exists for the case.
    """
    try:
        # Check if Google account is registered for this email
        is_google_account = any(
            e.value.lower() == email.lower()
            and e.metadata.get("registered") is True
            and e.platform
            and ("google" in e.platform.lower() or "gmail" in e.platform.lower())
            for e in target.entities
        )
        if not is_google_account and "@gmail.com" in email.lower():
            is_google_account = True

        if not is_google_account:
            return

        # Collect candidate names/usernames discovered so far for this target
        candidate_names = []
        for e in target.entities:
            if e.confidence >= 0.5:
                if e.entity_type in ("name", "username") and e.value:
                    candidate_names.append(e.value)

        # Deduplicate and remove generic or short values (< 3 chars)
        valid_candidates = []
        seen = set()
        for name in candidate_names:
            clean = name.strip()
            if len(clean) >= 3 and clean.lower() not in seen:
                seen.add(clean.lower())
                valid_candidates.append(clean)

        if not valid_candidates:
            return

        import modules.dork_fallback as dork_fallback
        import modules.evidence as evidence

        for candidate in valid_candidates[:2]:  # Limit to top 2 candidate queries
            dork_query = f'"{candidate}"'
            count, status = await dork_fallback.dork(
                target=target,
                query=dork_query,
                site_filter="google.com/maps/contrib",
                entity_type="profile_link",
                on_find=on_find,
                module_name="maps_contrib_dork",
            )

            if status == "success" and count > 0:
                # Capture screenshot for newly discovered maps contrib links
                for e in target.entities:
                    if (
                        e.entity_type == "profile_link"
                        and "maps/contrib" in e.value.lower()
                        and not e.metadata.get("screenshot_path")
                    ):
                        try:
                            entity_id = f"maps_contrib_{re.sub(r'[^a-zA-Z0-9_\-]', '_', candidate.lower())}"
                            cap_res = await evidence.capture(
                                e.value, target.case_slug, entity_id
                            )
                            if cap_res.get("success"):
                                e.metadata["screenshot_path"] = cap_res.get("screenshot_path")
                                e.metadata["verified"] = True
                        except Exception:
                            pass
    except Exception:
        pass
