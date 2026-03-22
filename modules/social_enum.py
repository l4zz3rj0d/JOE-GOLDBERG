# Username enumeration via Sherlock and Maigret (local, no API)
import subprocess
import json
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Tuple
from core.target_model import Entity, Target


async def run(
    target: Target,
    username: str,
    on_find=None,
) -> None:
    """
    Run Sherlock + Maigret against a username.
    Calls on_find(entity) callback for each discovery.
    """
    await _run_sherlock(target, username, on_find)
    await _run_maigret(target, username, on_find)


async def _run_sherlock(target, username, on_find):
    """Run sherlock CLI and parse results."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "sherlock", username,
            "--print-found",
            "--no-color",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        for line in stdout.decode().splitlines():
            if line.startswith("[+]"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    platform = parts[0].replace("[+]", "").strip()
                    url = parts[1].strip()
                    entity = Entity(
                        entity_type="username",
                        value=username,
                        sources=["sherlock"],
                        confidence=0.85,
                        platform=platform,
                        metadata={"url": url},
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)
    except FileNotFoundError:
        pass  # sherlock not installed — skip silently


async def _run_maigret(target, username, on_find):
    """Run maigret CLI and parse JSON output."""
    out_file = Path(f"/tmp/maigret_{username}.json")
    try:
        proc = await asyncio.create_subprocess_exec(
            "maigret", username,
            "--json", str(out_file),
            "-a",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        if out_file.exists():
            data = json.loads(out_file.read_text())
            for site, info in data.items():
                if info.get("status") == "Claimed":
                    entity = Entity(
                        entity_type="username",
                        value=username,
                        sources=["maigret"],
                        confidence=0.9,
                        platform=site,
                        metadata={"url": info.get("url", "")},
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)
            out_file.unlink(missing_ok=True)
    except FileNotFoundError:
        pass