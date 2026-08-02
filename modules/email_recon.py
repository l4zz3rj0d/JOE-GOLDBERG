import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import httpx
from core.target_model import Entity, Breach, Target


async def run(target: Target, email: str, on_find=None) -> None:
    await asyncio.gather(
        _check_breachdirectory(target, email, on_find),
        _check_holehe(target, email, on_find),
        _check_gravatar(target, email, on_find),
    )

    # Run multi-technique email intelligence enrichment (Gravatar, Libravatar, Google Maps dork)
    try:
        import modules.email_intel as email_intel
        await email_intel.enrich(target, email, on_find)
    except Exception:
        pass


async def _check_breachdirectory(target, email, on_find):
    """BreachDirectory free API — no key needed."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://breachdirectory.p.rapidapi.com/?func=auto&term={email}",
                headers={
                    "X-RapidAPI-Host": "breachdirectory.p.rapidapi.com",
                }
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("found"):
                    for item in data.get("result", []):
                        breach = Breach(
                            name=item.get("sources", ["Unknown"])[0],
                            date=item.get("last_breach", "Unknown"),
                            exposed_fields=item.get("fields", []),
                            source="breachdirectory",
                        )
                        target.add_breach(breach)
    except Exception:
        pass


async def _check_holehe(target, email, on_find):
    """Run holehe CLI to check email on 120+ sites."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "holehe", email, "--only-used", "--no-color",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        for line in stdout.decode(errors="ignore").splitlines():
            if "[+]" in line:
                # Extract site name
                site = line.split("[+]")[-1].strip().split()[0]
                entity = Entity(
                    entity_type="email",
                    value=email,
                    sources=["holehe"],
                    confidence=0.85,
                    platform=site,
                    metadata={"registered": True},
                )
                if target.add_entity(entity) and on_find:
                    await on_find(entity)

                # Follow-up profile enrichment if holehe detects Gravatar registration
                if "gravatar" in site.lower():
                    try:
                        import modules.gravatar_profile as gravatar_profile
                        await gravatar_profile.enrich(target, email, on_find)
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    except Exception:
        pass


async def _check_gravatar(target, email, on_find):
    """Check if email has a Gravatar — fetches public profile, name, location, links, avatar, screenshot."""
    try:
        import modules.gravatar_profile as gravatar_profile
        await gravatar_profile.enrich(target, email, on_find)
    except Exception:
        pass
