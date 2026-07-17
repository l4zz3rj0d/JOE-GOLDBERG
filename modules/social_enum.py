import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import json
from pathlib import Path as P
from core.target_model import Entity, Target
from modules.verify import verify_hit


async def run(target: Target, username: str, on_find=None, lessons_store=None) -> None:
    initial_count = len([e for e in target.entities if e.entity_type == "username" and e.value == username])

    await _run_sherlock(target, username, on_find, lessons_store)
    await _run_maigret(target, username, on_find, lessons_store)

    post_count = len([e for e in target.entities if e.entity_type == "username" and e.value == username])
    if post_count == initial_count:
        try:
            import modules.dork_fallback as dork_fallback
            count, _ = await dork_fallback.dork(target, username, site_filter="", entity_type="username", on_find=on_find, module_name="social_enum")
            try:
                from core.orchestrator import log_tool_fallback
                log_tool_fallback(target, "social_enum", count)
            except Exception:
                pass
        except Exception:
            pass

    await _run_instagram_probe(target, username, on_find, lessons_store)


async def _run_sherlock(target, username, on_find, lessons_store=None):
    try:
        proc = await asyncio.create_subprocess_exec(
            "sherlock", username,
            "--print-found", "--no-color", "--no-txt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            # Add 90s timeout to prevent Sherlock hanging forever
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90.0)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return
            
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
                    # Verify before trusting
                    case_slug = target.case_slug
                    entity = await verify_hit(entity, lessons_store=lessons_store, case_slug=case_slug)
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)
    except FileNotFoundError:
        pass
    except Exception:
        pass


async def _run_maigret(target, username, on_find, lessons_store=None):
    out_file = P(f"/tmp/maigret_{username}.json")
    try:
        proc = await asyncio.create_subprocess_exec(
            "maigret", username,
            "--json", str(out_file), "-a",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            # Add 90s timeout to prevent Maigret hanging forever
            await asyncio.wait_for(proc.communicate(), timeout=90.0)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return
            
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
                    # Verify before trusting
                    case_slug = target.case_slug
                    entity = await verify_hit(entity, lessons_store=lessons_store, case_slug=case_slug)
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)
            out_file.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    except Exception:
        pass


async def _run_instagram_probe(target, username, on_find, lessons_store=None):
    """
    Standalone Instagram check via headless probe.
    Always runs regardless of Sherlock/Maigret results — neither tool
    reliably covers Instagram.
    """
    try:
        from modules.headless_probe import probe as headless_probe
    except ImportError:
        return

    try:
        url = f"https://www.instagram.com/{username}/"
        slug = target.case_slug
        entity_id = f"username_{username}_instagram"
        evidence_dir = P(__file__).parent.parent / "cases" / slug / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(evidence_dir / f"{entity_id}.png")

        result = await headless_probe(url, "instagram", screenshot_path=screenshot_path)

        if result.get("exists"):
            entity = Entity(
                entity_type="username",
                value=username,
                sources=["headless_probe"],
                confidence=0.8,
                platform="Instagram",
                metadata={
                    "url": url,
                    "verified": True,
                    "page_title": result.get("title", ""),
                    "og_image": result.get("og_image"),
                    "description": result.get("og_description"),
                    "screenshot_path": f"cases/{slug}/evidence/{entity_id}.png",
                },
            )
            # Check lessons store for prior warnings
            if lessons_store:
                try:
                    warning = lessons_store.has_platform_warning("Instagram")
                    if warning:
                        entity.confidence *= 0.5
                        entity.metadata["lesson_warning"] = warning
                except Exception:
                    pass

            if target.add_entity(entity) and on_find:
                await on_find(entity)
    except Exception:
        pass
