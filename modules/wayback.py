import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import httpx
from core.target_model import Entity, Target


async def run(target: Target, domain: str, on_find=None) -> None:
    """Check Wayback Machine CDX API for historical snapshots."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"http://web.archive.org/cdx/search/cdx",
                params={
                    "url": f"*.{domain}",
                    "output": "json",
                    "fl": "original,timestamp,statuscode",
                    "collapse": "urlkey",
                    "limit": "20",
                    "filter": "statuscode:200",
                }
            )
            if r.status_code == 200:
                rows = r.json()
                # First row is header
                for row in rows[1:]:
                    if len(row) >= 2:
                        original_url = row[0]
                        timestamp = row[1]
                        year = timestamp[:4]

                        target.log("wayback_snapshot", {
                            "url": original_url,
                            "year": year,
                            "timestamp": timestamp,
                        })

                        # Extract unique subdomains
                        import re
                        subdomain_match = re.match(
                            rf"https?://([^/]+\.{re.escape(domain)})", original_url
                        )
                        if subdomain_match:
                            subdomain = subdomain_match.group(1)
                            entity = Entity(
                                entity_type="domain",
                                value=subdomain,
                                sources=["wayback"],
                                confidence=0.7,
                                platform="Wayback Machine",
                                metadata={"first_seen": year},
                            )
                            target.add_entity(entity)

    except Exception:
        pass
