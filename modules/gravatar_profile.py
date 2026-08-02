# modules/gravatar_profile.py
"""
Gravatar profile enrichment module.
Fetches public Gravatar JSON profile data, extracts real name, username, location,
linked sites/accounts, downloads avatar thumbnail, and captures profile page screenshot.
"""
import sys
import hashlib
import asyncio
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
    Enrich target with Gravatar profile data for a given email address.
    """
    if not email or not isinstance(email, str):
        return

    clean_email = email.strip().lower()
    email_hash = hashlib.md5(clean_email.encode("utf-8")).hexdigest()

    # Deduplication guard: check if gravatar_profile enrichment was already run for this email
    if any(
        "gravatar_profile" in e.sources and e.metadata.get("email_hash") == email_hash
        for e in target.entities
    ):
        return

    try:
        json_url = f"https://www.gravatar.com/{email_hash}.json"
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            r = await client.get(json_url)
            if r.status_code != 200:
                return

            try:
                data = r.json()
            except Exception:
                return

            entries = data.get("entry", [])
            if not entries:
                return

            entry = entries[0]

            display_name = entry.get("displayName")
            preferred_username = entry.get("preferredUsername")
            current_location = entry.get("currentLocation")
            about_me = entry.get("aboutMe")
            urls = entry.get("urls", [])
            accounts = entry.get("accounts", [])
            photos = entry.get("photos", [])
            thumbnail_url = entry.get("thumbnailUrl")

            profile_url = (
                f"https://en.gravatar.com/{preferred_username}"
                if preferred_username
                else f"https://gravatar.com/{email_hash}"
            )

            # 1. Download avatar image thumbnail for perceptual hash correlation
            avatar_url = thumbnail_url
            if not avatar_url and photos and isinstance(photos, list):
                avatar_url = photos[0].get("value")
            if not avatar_url:
                avatar_url = f"https://www.gravatar.com/avatar/{email_hash}?s=400"

            avatar_path = None
            if avatar_url:
                try:
                    img_res = await client.get(avatar_url)
                    if img_res.status_code == 200 and img_res.content:
                        evidence_dir = (
                            PROJECT_ROOT / "cases" / target.case_slug / "evidence"
                        )
                        evidence_dir.mkdir(parents=True, exist_ok=True)
                        avatar_filename = f"gravatar_avatar_{email_hash}.png"
                        avatar_file = evidence_dir / avatar_filename
                        avatar_file.write_bytes(img_res.content)
                        avatar_path = f"cases/{target.case_slug}/evidence/{avatar_filename}"
                except Exception:
                    pass

            # 2. Capture full-page visual screenshot of public Gravatar profile page
            screenshot_path = None
            try:
                import modules.evidence as evidence

                entity_id = f"gravatar_profile_{email_hash}"
                cap_res = await evidence.capture(
                    profile_url, target.case_slug, entity_id
                )
                if cap_res.get("success"):
                    screenshot_path = cap_res.get("screenshot_path")
            except Exception:
                pass

            # Prepare common metadata shared across emitted entities
            base_meta = {
                "email": clean_email,
                "email_hash": email_hash,
                "profile": profile_url,
                "verified": True,
            }
            if current_location:
                base_meta["location"] = current_location
            if about_me:
                base_meta["bio"] = about_me
            if avatar_path:
                base_meta["avatar_path"] = avatar_path
            if screenshot_path:
                base_meta["screenshot_path"] = screenshot_path

            # Emit display name
            if display_name:
                name_entity = Entity(
                    entity_type="name",
                    value=display_name,
                    sources=["gravatar_profile"],
                    confidence=0.85,
                    platform="Gravatar",
                    metadata=dict(base_meta),
                )
                if target.add_entity(name_entity) and on_find:
                    await on_find(name_entity)

            # Emit preferred username
            if preferred_username:
                uname_entity = Entity(
                    entity_type="username",
                    value=preferred_username,
                    sources=["gravatar_profile"],
                    confidence=0.85,
                    platform="Gravatar",
                    metadata=dict(base_meta, url=profile_url),
                )
                if target.add_entity(uname_entity) and on_find:
                    await on_find(uname_entity)

            # Emit linked URLs
            if isinstance(urls, list):
                for u in urls:
                    if isinstance(u, dict):
                        u_val = u.get("value")
                        u_title = u.get("title") or "Gravatar Linked Site"
                        if u_val:
                            link_entity = Entity(
                                entity_type="profile_link",
                                value=u_val,
                                sources=["gravatar_profile"],
                                confidence=0.85,
                                platform=u_title,
                                metadata=dict(base_meta, url=u_val),
                            )
                            if target.add_entity(link_entity) and on_find:
                                await on_find(link_entity)

            # Emit linked accounts
            if isinstance(accounts, list):
                for acc in accounts:
                    if isinstance(acc, dict):
                        acc_url = acc.get("url")
                        acc_plat = (
                            acc.get("shortname")
                            or acc.get("domain")
                            or acc.get("name")
                            or "Gravatar Linked Account"
                        )
                        if acc_url:
                            acc_entity = Entity(
                                entity_type="profile_link",
                                value=acc_url,
                                sources=["gravatar_profile"],
                                confidence=0.85,
                                platform=acc_plat,
                                metadata=dict(
                                    base_meta,
                                    url=acc_url,
                                    account_name=acc.get("display") or acc.get("username"),
                                ),
                            )
                            if target.add_entity(acc_entity) and on_find:
                                await on_find(acc_entity)

            # Fallback if neither display_name nor preferred_username was present
            if not display_name and not preferred_username:
                profile_entity = Entity(
                    entity_type="profile_link",
                    value=profile_url,
                    sources=["gravatar_profile"],
                    confidence=0.85,
                    platform="Gravatar",
                    metadata=dict(base_meta, url=profile_url),
                )
                if target.add_entity(profile_entity) and on_find:
                    await on_find(profile_entity)

    except Exception:
        # Graceful degradation
        pass
