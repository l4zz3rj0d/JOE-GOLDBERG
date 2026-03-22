import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
from typing import Callable
from core.input_parser import parse
from core.target_model import Target, Entity
import modules.social_enum as social
import modules.domain_intel as domain
# ... rest of file unchanged


class Orchestrator:
    def __init__(
        self,
        on_status: Callable = None,
        on_find: Callable = None,
        on_done: Callable = None,
    ):
        self.on_status = on_status
        self.on_find = on_find
        self.on_done = on_done

    async def stalk(self, raw_input: str) -> Target:
        parsed = parse(raw_input)
        target = Target(primary=parsed.value, target_type=parsed.target_type)

        await self._status(f"Parsed as {parsed.target_type}: {parsed.value}")

        if parsed.target_type == "email":
            await self._status("Extracting username patterns from email...")
            await self._email_pipeline(target, parsed)

        elif parsed.target_type == "username":
            await self._status("Scanning 300+ platforms for username...")
            await social.run(target, parsed.value, self._make_find_cb(target))

        elif parsed.target_type == "domain":
            await self._status("Running domain intelligence...")
            await domain.run(target, parsed.value, self._make_find_cb(target))

        elif parsed.target_type == "ip":
            await self._status("Resolving IP intelligence...")
            await self._ip_pipeline(target, parsed)

        elif parsed.target_type == "name":
            await self._status(f"Searching for name: {parsed.value}")
            await self._name_pipeline(target, parsed)

        target.compute_risk()
        target.save()

        if self.on_done:
            await self.on_done(target)

        return target

    async def _email_pipeline(self, target, parsed):
        local = parsed.metadata["local"]
        dom = parsed.metadata["domain"]

        candidates = list(set([
            local,
            local.replace(".", "_"),
            local.replace(".", ""),
            local.split(".")[0] if "." in local else local,
        ]))

        await self._status(f"Scanning {len(candidates)} username variants...")
        for uname in candidates:
            await social.run(target, uname, self._make_find_cb(target))

        generic = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}
        if dom not in generic:
            await self._status(f"Running domain intel on {dom}...")
            await domain.run(target, dom, self._make_find_cb(target))

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
        await self._status(f"Trying {len(candidates)} username variants for {parsed.value}...")
        for uname in candidates:
            await social.run(target, uname, self._make_find_cb(target))

    async def _ip_pipeline(self, target, parsed):
        import socket
        try:
            hostname = socket.gethostbyaddr(parsed.value)[0]
            await self._status(f"Reverse DNS: {hostname}")
            target.log("reverse_dns", {"ip": parsed.value, "host": hostname})
        except:
            pass

    def _make_find_cb(self, target: Target):
        async def _cb(entity: Entity):
            if self.on_find:
                await self.on_find(entity, target)
        return _cb

    async def _status(self, msg: str):
        if self.on_status:
            await self.on_status(msg)