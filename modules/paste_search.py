import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import httpx
import re
from core.target_model import Entity, Target


async def run(target: Target, query: str, on_find=None) -> None:
    await asyncio.gather(
        _search_psbdmp(target, query, on_find),
        _search_pastebin_google(target, query, on_find),
    )


async def _search_psbdmp(target, query, on_find):
    """psbdmp.cc — public paste search, no key needed."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://psbdmp.cc/api/v3/search/{query}",
            )
            if r.status_code == 200:
                data = r.json()
                for paste in data.get("data", [])[:5]:
                    paste_id = paste.get("id")
                    entity = Entity(
                        entity_type="paste",
                        value=f"https://pastebin.com/{paste_id}",
                        sources=["psbdmp"],
                        confidence=0.7,
                        platform="Pastebin",
                        metadata={
                            "id": paste_id,
                            "tags": paste.get("tags", ""),
                            "query": query
                        },
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)
    except Exception:
        pass


async def _search_pastebin_google(target, query, on_find):
    """Scrape Google for pastebin mentions of the query."""
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
        ) as client:
            r = await client.get(
                f"https://www.google.com/search?q=site:pastebin.com+{query}",
            )
            if r.status_code == 200:
                urls = re.findall(
                    r'pastebin\.com/[a-zA-Z0-9]+', r.text
                )
                seen = set()
                for url in urls[:3]:
                    full_url = f"https://{url}"
                    if full_url not in seen:
                        seen.add(full_url)
                        entity = Entity(
                            entity_type="paste",
                            value=full_url,
                            sources=["google_dork"],
                            confidence=0.65,
                            platform="Pastebin",
                            metadata={"query": query},
                        )
                        if target.add_entity(entity) and on_find:
                            await on_find(entity)
    except Exception:
        pass
