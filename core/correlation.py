# core/correlation.py
"""
Phase 3: Correlation Engine
Analyzes discovered entities pairwise, bumps their confidence based on signal strength,
and logs correlation_found events to the timeline.
"""
import asyncio
import re
from pathlib import Path
from typing import List, Optional
from core.target_model import Target, Entity

# Multipliers per signal strength
MULTIPLIERS = {
    "avatar_match": 1.20,
    "bio_match": 1.15,
    "name_match": 1.05,
    "location_match": 1.05
}


def get_entity_id(entity: Entity) -> str:
    plat = entity.platform or "unknown"
    return f"{entity.entity_type}:{entity.value}:{plat}"


def normalize_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


def get_entity_names(entity: Entity) -> List[str]:
    names = []
    if entity.entity_type == "name":
        names.append(entity.value)
    if entity.metadata.get("name"):
        names.append(entity.metadata["name"])
    return [n for n in names if n]


def check_name_match(entity_a: Entity, entity_b: Entity) -> bool:
    names_a = get_entity_names(entity_a)
    names_b = get_entity_names(entity_b)
    
    for na in names_a:
        norm_a = normalize_name(na)
        if not norm_a or len(norm_a) < 3:
            continue
        for nb in names_b:
            norm_b = normalize_name(nb)
            if not norm_b or len(norm_b) < 3:
                continue
            if norm_a == norm_b:
                return True
            # Near-match variant logic:
            # If both normalized names are >= 5 characters and one is a substring of the other, return True.
            if len(norm_a) >= 5 and len(norm_b) >= 5:
                if norm_a in norm_b or norm_b in norm_a:
                    return True
    return False


def get_entity_descriptions(entity: Entity) -> List[str]:
    descs = []
    if entity.metadata.get("bio"):
        descs.append(entity.metadata["bio"])
    if entity.metadata.get("description"):
        descs.append(entity.metadata["description"])
    return [d for d in descs if d]


def longest_common_substring(s1: str, s2: str) -> str:
    s1 = " ".join(s1.lower().split())
    s2 = " ".join(s2.lower().split())
    
    if not s1 or not s2:
        return ""
    
    m = [[0] * (1 + len(s2)) for _ in range(1 + len(s1))]
    longest, x_longest = 0, 0
    for x in range(1, 1 + len(s1)):
        for y in range(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
    return s1[x_longest - longest: x_longest]


def check_bio_match(entity_a: Entity, entity_b: Entity) -> bool:
    descs_a = get_entity_descriptions(entity_a)
    descs_b = get_entity_descriptions(entity_b)
    
    for da in descs_a:
        for db in descs_b:
            lcs = longest_common_substring(da, db)
            if len(lcs) >= 25:
                return True
    return False


def crop_avatar(image, platform: str):
    if not platform:
        return image
    
    w, h = image.size
    plat = platform.lower()
    
    if "github" in plat:
        return image.crop((int(w * 0.02), int(h * 0.12), int(w * 0.28), int(h * 0.50)))
    elif "instagram" in plat:
        return image.crop((int(w * 0.05), int(h * 0.05), int(w * 0.35), int(h * 0.35)))
    elif "twitter" in plat or "x" in plat:
        return image.crop((int(w * 0.05), int(h * 0.15), int(w * 0.30), int(h * 0.40)))
    return image


def _compute_phash_dist(file_a: str, platform_a: str, file_b: str, platform_b: str) -> int:
    import imagehash
    from PIL import Image
    
    with Image.open(file_a) as img_a, Image.open(file_b) as img_b:
        img_a = img_a.convert("RGB")
        img_b = img_b.convert("RGB")
        
        try:
            crop_a = crop_avatar(img_a, platform_a)
        except Exception:
            crop_a = img_a
            
        try:
            crop_b = crop_avatar(img_b, platform_b)
        except Exception:
            crop_b = img_b
            
        hash_a = imagehash.phash(crop_a)
        hash_b = imagehash.phash(crop_b)
        
        return hash_a - hash_b


async def check_avatar_match(entity_a: Entity, entity_b: Entity) -> bool:
    path_a = entity_a.metadata.get("avatar_path") or entity_a.metadata.get("screenshot_path")
    path_b = entity_b.metadata.get("avatar_path") or entity_b.metadata.get("screenshot_path")
    if not path_a or not path_b:
        return False
    
    if path_a == path_b:
        return False
        
    PROJECT_ROOT = Path(__file__).parent.parent
    file_a = PROJECT_ROOT / path_a
    file_b = PROJECT_ROOT / path_b
    
    if not file_a.exists() or not file_b.exists():
        return False
        
    loop = asyncio.get_running_loop()
    try:
        dist = await loop.run_in_executor(
            None, 
            _compute_phash_dist, 
            str(file_a), 
            entity_a.platform or "", 
            str(file_b), 
            entity_b.platform or ""
        )
        return dist <= 5
    except Exception:
        return False


def check_location_match(entity_a: Entity, entity_b: Entity) -> bool:
    loc_a = entity_a.metadata.get("location") or ""
    loc_b = entity_b.metadata.get("location") or ""
    
    norm_a = re.sub(r"[^a-zA-Z0-9]", "", loc_a).lower()
    norm_b = re.sub(r"[^a-zA-Z0-9]", "", loc_b).lower()
    
    if norm_a and norm_b and len(norm_a) >= 3:
        return norm_a == norm_b
    return False


async def correlate(target: Target) -> int:
    """
    Correlates entities in target.entities pairwise.
    Bumps confidence of corroborating entities and logs correlation_found events.
    Returns the count of corroborations found.
    """
    corroboration_count = 0
    
    # Filter out entities that are low-confidence mentions
    entities = [
        e for e in target.entities 
        if e.entity_type != "mention" and e.confidence > 0.2
    ]
    
    n = len(entities)
    for i in range(n):
        for j in range(i + 1, n):
            entity_a = entities[i]
            entity_b = entities[j]
            
            # Check name_match
            try:
                if check_name_match(entity_a, entity_b):
                    corroboration_count += 1
                    conf_before = entity_a.confidence
                    mult = MULTIPLIERS["name_match"]
                    entity_a.confidence = min(entity_a.confidence * mult, 0.99)
                    entity_b.confidence = min(entity_b.confidence * mult, 0.99)
                    target.log("correlation_found", {
                        "entity_a": get_entity_id(entity_a),
                        "entity_b": get_entity_id(entity_b),
                        "signal": "name_match",
                        "confidence_before": conf_before,
                        "confidence_after": entity_a.confidence
                    })
            except Exception:
                pass
                
            # Check bio_match
            try:
                if check_bio_match(entity_a, entity_b):
                    corroboration_count += 1
                    conf_before = entity_a.confidence
                    mult = MULTIPLIERS["bio_match"]
                    entity_a.confidence = min(entity_a.confidence * mult, 0.99)
                    entity_b.confidence = min(entity_b.confidence * mult, 0.99)
                    target.log("correlation_found", {
                        "entity_a": get_entity_id(entity_a),
                        "entity_b": get_entity_id(entity_b),
                        "signal": "bio_match",
                        "confidence_before": conf_before,
                        "confidence_after": entity_a.confidence
                    })
            except Exception:
                pass
                
            # Check avatar_match
            try:
                if await check_avatar_match(entity_a, entity_b):
                    corroboration_count += 1
                    conf_before = entity_a.confidence
                    mult = MULTIPLIERS["avatar_match"]
                    entity_a.confidence = min(entity_a.confidence * mult, 0.99)
                    entity_b.confidence = min(entity_b.confidence * mult, 0.99)
                    target.log("correlation_found", {
                        "entity_a": get_entity_id(entity_a),
                        "entity_b": get_entity_id(entity_b),
                        "signal": "avatar_match",
                        "confidence_before": conf_before,
                        "confidence_after": entity_a.confidence
                    })
            except Exception:
                pass
                
            # Check location_match
            try:
                if check_location_match(entity_a, entity_b):
                    corroboration_count += 1
                    conf_before = entity_a.confidence
                    mult = MULTIPLIERS["location_match"]
                    entity_a.confidence = min(entity_a.confidence * mult, 0.99)
                    entity_b.confidence = min(entity_b.confidence * mult, 0.99)
                    target.log("correlation_found", {
                        "entity_a": get_entity_id(entity_a),
                        "entity_b": get_entity_id(entity_b),
                        "signal": "location_match",
                        "confidence_before": conf_before,
                        "confidence_after": entity_a.confidence
                    })
            except Exception:
                pass
                
    return corroboration_count
