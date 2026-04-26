import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import httpx
from core.target_model import Entity, Target


async def run(target: Target, ip: str, on_find=None) -> None:
    await asyncio.gather(
        _geolocate(target, ip, on_find),
        _check_abuse(target, ip, on_find),
        _reverse_dns(target, ip, on_find),
    )


async def _geolocate(target, ip, on_find):
    """ip-api.com — free, no key, 45 req/min."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,as,reverse,mobile,proxy,hosting"
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "success":
                    target.log("ip_geo", {
                        "ip": ip,
                        "country": data.get("country"),
                        "city": data.get("city"),
                        "isp": data.get("isp"),
                        "org": data.get("org"),
                        "is_proxy": data.get("proxy"),
                        "is_hosting": data.get("hosting"),
                        "reverse_dns": data.get("reverse"),
                    })

                    # Flag if proxy or VPN
                    if data.get("proxy"):
                        target.log("proxy_detected", {"ip": ip})

    except Exception:
        pass


async def _check_abuse(target, ip, on_find):
    """AbuseIPDB free check via scraping."""
    try:
        async with httpx.AsyncClient(
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            r = await client.get(f"https://www.abuseipdb.com/check/{ip}")
            if r.status_code == 200 and "reports" in r.text.lower():
                target.log("abuse_check", {"ip": ip, "url": f"https://www.abuseipdb.com/check/{ip}"})
    except Exception:
        pass


async def _reverse_dns(target, ip, on_find):
    """Reverse DNS lookup."""
    import socket
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        entity = Entity(
            entity_type="domain",
            value=hostname,
            sources=["reverse_dns"],
            confidence=0.9,
            platform="DNS",
            metadata={"ip": ip},
        )
        if target.add_entity(entity) and on_find:
            await on_find(entity)
    except Exception:
        pass
