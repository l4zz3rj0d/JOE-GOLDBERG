# Domain and IP intelligence — zero API keys required
import asyncio
import socket
import httpx
import whois
import dns.resolver
from core.target_model import Entity, Target


async def run(target: Target, domain: str, on_find=None) -> None:
    await asyncio.gather(
        _whois_lookup(target, domain, on_find),
        _dns_records(target, domain, on_find),
        _crt_sh(target, domain, on_find),
    )


async def _whois_lookup(target, domain, on_find):
    try:
        loop = asyncio.get_event_loop()
        w = await loop.run_in_executor(None, whois.whois, domain)
        if w.emails:
            emails = [w.emails] if isinstance(w.emails, str) else w.emails
            for email in emails:
                entity = Entity(
                    entity_type="email",
                    value=email.lower(),
                    sources=["whois"],
                    confidence=0.75,
                    metadata={"registrar": str(w.registrar)},
                )
                if target.add_entity(entity) and on_find:
                    await on_find(entity)
        if w.org:
            target.log("whois_org", {"org": str(w.org), "domain": domain})
    except:
        pass


async def _dns_records(target, domain, on_find):
    record_types = ["A", "MX", "TXT", "NS"]
    for rtype in record_types:
        try:
            answers = dns.resolver.resolve(domain, rtype)
            for r in answers:
                val = str(r).rstrip(".")
                if rtype == "A":
                    entity = Entity(
                        entity_type="ip",
                        value=val,
                        sources=["dns"],
                        confidence=0.95,
                        metadata={"record_type": rtype, "domain": domain},
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)
                target.log(f"dns_{rtype.lower()}", {"value": val})
        except:
            pass


async def _crt_sh(target, domain, on_find):
    """Scrape crt.sh for certificate transparency logs — no key."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://crt.sh/?q=%.{domain}&output=json"
            )
            seen = set()
            for cert in r.json():
                name = cert.get("name_value", "").lower()
                for sub in name.splitlines():
                    sub = sub.strip().lstrip("*.")
                    if sub and sub not in seen and domain in sub:
                        seen.add(sub)
                        entity = Entity(
                            entity_type="domain",
                            value=sub,
                            sources=["crt.sh"],
                            confidence=0.8,
                            metadata={"parent": domain},
                        )
                        if target.add_entity(entity) and on_find:
                            await on_find(entity)
    except:
        pass