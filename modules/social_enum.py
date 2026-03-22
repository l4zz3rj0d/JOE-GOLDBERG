import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import json
from pathlib import Path as P
from core.target_model import Entity, Target


async def run(target: Target, username: str, on_find=None) -> None:
    await _run_sherlock(target, username, on_find)
    await _run_maigret(target, username, on_find)


async def _run_sherlock(target, username, on_find):
    try:
        proc = await asyncio.create_subprocess_exec(
            "sherlock", username,
            "--print-found", "--no-color",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        for line in stdout.decode(errors="ignore").splitlines():
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
        pass
    except Exception:
        pass


async def _run_maigret(target, username, on_find):
    out_file = P(f"/tmp/maigret_{username}.json")
    try:
        proc = await asyncio.create_subprocess_exec(
            "maigret", username,
            "--json", str(out_file), "-a",
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
    except Exception:
        pass
