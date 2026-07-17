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


import ipaddress

# Known ranges for shared static CDN/hosting platforms
KNOWN_RANGES = {
    "GitHub Pages": [
        ipaddress.ip_network("185.199.108.0/22"),
        ipaddress.ip_network("140.82.112.0/20"),  # GitHub
    ],
    "Cloudflare": [
        ipaddress.ip_network("173.245.48.0/20"),
        ipaddress.ip_network("103.21.244.0/22"),
        ipaddress.ip_network("103.22.200.0/22"),
        ipaddress.ip_network("103.31.4.0/22"),
        ipaddress.ip_network("141.101.64.0/18"),
        ipaddress.ip_network("108.162.192.0/18"),
        ipaddress.ip_network("190.93.240.0/20"),
        ipaddress.ip_network("188.114.96.0/20"),
        ipaddress.ip_network("197.234.240.0/22"),
        ipaddress.ip_network("198.41.128.0/17"),
        ipaddress.ip_network("162.158.0.0/15"),
        ipaddress.ip_network("104.16.0.0/13"),
        ipaddress.ip_network("172.64.0.0/13"),
        ipaddress.ip_network("131.0.72.0/22"),
    ],
    "Fastly": [
        ipaddress.ip_network("151.101.0.0/16"),
    ]
}

KNOWN_PROVIDERS = [
    # (lowercase_keyword, display_name)
    ("netlify", "Netlify"),
    ("vercel", "Vercel"),
    ("github", "GitHub"),
    ("cloudflare", "Cloudflare"),
    ("fastly", "Fastly"),
    ("amazon", "AWS"),
    ("aws", "AWS"),
    ("google", "Google Cloud"),
    ("microsoft", "Azure"),
    ("azure", "Azure"),
    ("digitalocean", "DigitalOcean"),
    ("linode", "Linode"),
    ("hetzner", "Hetzner"),
    ("ovh", "OVH"),
]


def check_shared_infrastructure(ip_str: str, isp: str = "", org: str = "") -> tuple[bool, str]:
    # Check IP CIDR ranges
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for provider, networks in KNOWN_RANGES.items():
            for net in networks:
                if ip_obj in net:
                    return True, provider
    except ValueError:
        pass

    # Check ISP / Org keywords
    isp_lower = (isp or "").lower()
    org_lower = (org or "").lower()
    for kw, display_name in KNOWN_PROVIDERS:
        if kw in isp_lower or kw in org_lower:
            return True, display_name

    return False, ""


async def _geolocate(target, ip, on_find):
    """ip-api.com — free, no key, 45 req/min."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,lat,lon,isp,org,as,reverse,mobile,proxy,hosting"
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "success":
                    is_shared, provider = check_shared_infrastructure(
                        ip, data.get("isp"), data.get("org")
                    )

                    target.log("ip_geo", {
                        "ip": ip,
                        "country": data.get("country"),
                        "city": data.get("city"),
                        "lat": data.get("lat"),
                        "lon": data.get("lon"),
                        "isp": data.get("isp"),
                        "org": data.get("org"),
                        "is_proxy": data.get("proxy"),
                        "is_hosting": data.get("hosting") or is_shared,
                        "reverse_dns": data.get("reverse"),
                        "hosting_provider": provider if is_shared else None,
                        "is_shared_infrastructure": is_shared,
                    })

                    # Also update metadata on the existing Entity in target
                    for e in target.entities:
                        if e.entity_type == "ip" and e.value == ip:
                            e.metadata["country"] = data.get("country")
                            e.metadata["city"] = data.get("city")
                            e.metadata["lat"] = data.get("lat")
                            e.metadata["lon"] = data.get("lon")
                            e.metadata["isp"] = data.get("isp")
                            e.metadata["org"] = data.get("org")
                            e.metadata["is_proxy"] = data.get("proxy")
                            e.metadata["is_hosting"] = data.get("hosting") or is_shared
                            e.metadata["hosting_provider"] = provider if is_shared else None
                            e.metadata["is_shared_infrastructure"] = is_shared

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
