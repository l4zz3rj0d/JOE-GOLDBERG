import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
import httpx
from core.target_model import Entity, Target


async def run(target: Target, query: str, query_type: str = "user", on_find=None) -> None:
    """
    query_type: 'user' | 'email' | 'keyword'
    """
    await asyncio.gather(
        _search_commits(target, query, on_find),
        _search_code(target, query, on_find),
        _get_user_profile(target, query, on_find),
    )


async def _get_user_profile(target, username, on_find):
    """Pull public GitHub profile — reveals email, name, bio."""
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Joe-Goldberg-OSINT"}
        ) as client:
            r = await client.get(f"https://api.github.com/users/{username}")
            if r.status_code == 200:
                data = r.json()

                # Real name
                if data.get("name"):
                    entity = Entity(
                        entity_type="name",
                        value=data["name"],
                        sources=["github"],
                        confidence=0.8,
                        platform="GitHub",
                        metadata={"username": username}
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)

                # Public email
                if data.get("email"):
                    entity = Entity(
                        entity_type="email",
                        value=data["email"],
                        sources=["github"],
                        confidence=0.9,
                        platform="GitHub",
                        metadata={"username": username}
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)

                # Location
                if data.get("location"):
                    target.log("github_location", {
                        "username": username,
                        "location": data["location"]
                    })

                # Blog/website
                if data.get("blog"):
                    entity = Entity(
                        entity_type="domain",
                        value=data["blog"],
                        sources=["github"],
                        confidence=0.75,
                        platform="GitHub",
                        metadata={"username": username}
                    )
                    if target.add_entity(entity) and on_find:
                        await on_find(entity)

    except Exception:
        pass


async def _search_commits(target, query, on_find):
    """Search commit history for email leaks."""
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Joe-Goldberg-OSINT"}
        ) as client:
            r = await client.get(
                f"https://api.github.com/search/commits?q={query}&per_page=5",
                headers={"Accept": "application/vnd.github.cloak-preview"}
            )
            if r.status_code == 200:
                for item in r.json().get("items", []):
                    commit = item.get("commit", {})
                    author = commit.get("author", {})
                    email = author.get("email", "")
                    name = author.get("name", "")

                    if email and "@" in email and "noreply" not in email:
                        entity = Entity(
                            entity_type="email",
                            value=email.lower(),
                            sources=["github_commits"],
                            confidence=0.85,
                            platform="GitHub",
                            metadata={
                                "name": name,
                                "repo": item.get("repository", {}).get("full_name", ""),
                                "commit_url": item.get("html_url", "")
                            }
                        )
                        if target.add_entity(entity) and on_find:
                            await on_find(entity)
    except Exception:
        pass


async def _search_code(target, query, on_find):
    """Search GitHub code for mentions of email/username."""
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Joe-Goldberg-OSINT"}
        ) as client:
            r = await client.get(
                f"https://api.github.com/search/code?q={query}&per_page=3"
            )
            if r.status_code == 200:
                for item in r.json().get("items", []):
                    target.log("github_code_mention", {
                        "query": query,
                        "repo": item.get("repository", {}).get("full_name", ""),
                        "file": item.get("name", ""),
                        "url": item.get("html_url", "")
                    })
    except Exception:
        pass
