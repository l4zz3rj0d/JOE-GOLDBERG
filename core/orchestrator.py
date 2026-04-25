import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
from core.input_parser import parse
from core.target_model import Target, Entity
import modules.social_enum as social
import modules.domain_intel as domain
import modules.email_recon as email_recon
import modules.paste_search as paste_search
import modules.github_recon as github_recon
import modules.ip_recon as ip_recon
import modules.wayback as wayback


class Orchestrator:
    def __init__(self, on_status=None, on_find=None, on_done=None):
        self.on_status = on_status
        self.on_find = on_find
        self.on_done = on_done

    async def stalk(self, raw_input: str) -> Target:
        parsed = parse(raw_input)
        target = Target(primary=parsed.value, target_type=parsed.target_type)

        await self._status(f"Parsed as {parsed.target_type}: {parsed.value}")

        if parsed.target_type == "email":
            await self._email_pipeline(target, parsed)
        elif parsed.target_type == "username":
            await self._username_pipeline(target, parsed)
        elif parsed.target_type == "domain":
            await self._domain_pipeline(target, parsed)
        elif parsed.target_type == "ip":
            await self._ip_pipeline(target, parsed)
        elif parsed.target_type == "name":
            await self._name_pipeline(target, parsed)

        target.compute_risk()
        target.save()

        if self.on_done:
            await self.on_done(target)

        return target

    async def _email_pipeline(self, target, parsed):
        local = parsed.metadata["local"]
        dom = parsed.metadata["domain"]

        await self._status("Running email breach lookup...")
        await email_recon.run(target, parsed.value, self._make_find_cb(target))

        await self._status("Searching paste sites...")
        await paste_search.run(target, parsed.value, self._make_find_cb(target))

        await self._status("Scanning username variants across 300+ platforms...")
        candidates = list(set([
            local,
            local.replace(".", "_"),
            local.replace(".", ""),
            local.split(".")[0] if "." in local else local,
        ]))
        for uname in candidates:
            await social.run(target, uname, self._make_find_cb(target))
            await github_recon.run(target, uname, on_find=self._make_find_cb(target))

        generic = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}
        if dom not in generic:
            await self._status(f"Running domain intel on {dom}...")
            await domain.run(target, dom, self._make_find_cb(target))
            await wayback.run(target, dom, self._make_find_cb(target))

    async def _username_pipeline(self, target, parsed):
        await self._status("Scanning 300+ platforms for username...")
        await social.run(target, parsed.value, self._make_find_cb(target))

        await self._status("Running GitHub deep recon...")
        await github_recon.run(target, parsed.value, on_find=self._make_find_cb(target))

        await self._status("Searching paste sites...")
        await paste_search.run(target, parsed.value, self._make_find_cb(target))

    async def _domain_pipeline(self, target, parsed):
        await self._status("Running domain intelligence...")
        await domain.run(target, parsed.value, self._make_find_cb(target))

        await self._status("Checking Wayback Machine...")
        await wayback.run(target, parsed.value, self._make_find_cb(target))

        await self._status("Searching paste sites...")
        await paste_search.run(target, parsed.value, self._make_find_cb(target))

    async def _ip_pipeline(self, target, parsed):
        await self._status("Geolocating IP...")
        await ip_recon.run(target, parsed.value, self._make_find_cb(target))

    async def _name_pipeline(self, target, parsed):
        first = parsed.metadata["first"]
        last = parsed.metadata["last"]
        candidates = list(set([
            f"{first}{last}",
            f"{first}.{last}",
            f"{first}_{last}",
            f"{first[0]}{last}",
            first,
        ]))
        await self._status(f"Trying {len(candidates)} username variants...")
        for uname in candidates:
            await social.run(target, uname, self._make_find_cb(target))
            await github_recon.run(target, uname, on_find=self._make_find_cb(target))

        await self._status("Searching paste sites...")
        await paste_search.run(target, parsed.value, self._make_find_cb(target))

    def _make_find_cb(self, target: Target):
        async def _cb(entity: Entity):
            if self.on_find:
                await self.on_find(entity, target)
        return _cb

    async def _status(self, msg: str):
        if self.on_status:
            await self.on_status(msg)