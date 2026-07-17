# modules/geocode.py
import json
import re
from pathlib import Path

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
CITIES_JSON = DATA_DIR / "cities.json"

# Cached indexes
_DATA = None
_CITY_INDEX = {}      # lowercase name -> list of city entries (sorted by pop desc)
_COUNTRY_INDEX = {}   # lowercase name -> country entry
_REGION_INDEX = {}    # lowercase name -> region entry

def _init_indexes():
    global _DATA, _CITY_INDEX, _COUNTRY_INDEX, _REGION_INDEX
    if _DATA is not None:
        return
    
    if not CITIES_JSON.exists():
        _DATA = {"cities": [], "countries": [], "regions": []}
        return
        
    try:
        with open(CITIES_JSON, "r", encoding="utf-8") as f:
            _DATA = json.load(f)
    except Exception as e:
        print(f"[geocode] Error reading cities.json: {e}")
        _DATA = {"cities": [], "countries": [], "regions": []}
        return

    # Build country index
    for c in _DATA.get("countries", []):
        name_lower = c["name"].lower()
        _COUNTRY_INDEX[name_lower] = c
        _COUNTRY_INDEX[c["cc"].lower()] = c  # support ISO code as well

    # Build region index
    for r in _DATA.get("regions", []):
        name_lower = r["name"].lower()
        # If duplicate name, keep the one we encounter first (or we could store lists, but single match is usually fine for centroids)
        if name_lower not in _REGION_INDEX:
            _REGION_INDEX[name_lower] = r

    # Build city index
    for city in _DATA.get("cities", []):
        names = [city["n"].lower()]
        if "a" in city:
            names.extend([alt.lower() for alt in city["a"]])
            
        for name in names:
            if name not in _CITY_INDEX:
                _CITY_INDEX[name] = []
            _CITY_INDEX[name].append(city)

    # Sort cities under each name by population descending
    for name in _CITY_INDEX:
        _CITY_INDEX[name].sort(key=lambda x: x.get("p", 0), reverse=True)


def clean_string(s: str) -> str:
    """Lowercase and remove non-alphanumeric/spaces."""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def geocode(location_text: str) -> dict | None:
    """
    Geocodes a text string using local gazetteer index.
    Returns:
        dict: {"lat": float, "lng": float, "precision": "city"|"region"|"country"}
        None: if no match is found.
    """
    if not location_text or not isinstance(location_text, str):
        return None
        
    _init_indexes()
    
    # 1. Clean and tokenize by commas or semicolons
    parts = [clean_string(p) for p in re.split(r"[,;]+", location_text) if clean_string(p)]
    if not parts:
        # Try splitting by spaces/slashes if no commas
        parts = [clean_string(p) for p in re.split(r"[\s/]+", location_text) if clean_string(p)]
        
    if not parts:
        return None

    # Step A: Identify which tokens are country names
    country_cc = None
    country_match = None
    country_match_token = None
    country_parts = set()
    for part in parts:
        if part in _COUNTRY_INDEX:
            country_match = _COUNTRY_INDEX[part]
            country_cc = country_match["cc"]
            country_match_token = part
            country_parts.add(part)

    # Step B: Filter out country tokens for city/region matches unless we ONLY have country tokens
    non_country_parts = [p for p in parts if p not in country_parts]
    search_parts = non_country_parts if non_country_parts else parts

    # Step C: Check for city matches in search_parts
    for part in search_parts:
        if part in _CITY_INDEX:
            candidates = _CITY_INDEX[part]
            if country_cc:
                cc_candidates = [c for c in candidates if c["cc"].lower() == country_cc.lower()]
                if cc_candidates:
                    best = cc_candidates[0]
                    return {"lat": best["lat"], "lng": best["lng"], "precision": "city"}
                # Soft fallback for 2-letter country/state code collision (e.g., CA for California vs Canada)
                if country_match_token and len(country_match_token) == 2:
                    best = candidates[0]
                    return {"lat": best["lat"], "lng": best["lng"], "precision": "city"}
            if not country_cc:
                best = candidates[0]
                return {"lat": best["lat"], "lng": best["lng"], "precision": "city"}

    # Step D: Check for region matches in search_parts
    for part in search_parts:
        if part in _REGION_INDEX:
            r = _REGION_INDEX[part]
            if country_cc and r["cc"].lower() != country_cc.lower():
                continue
            return {"lat": r["lat"], "lng": r["lng"], "precision": "region"}

    # Step E: If we matched a country code but no city/region, return country centroid
    if country_match:
        return {"lat": country_match["lat"], "lng": country_match["lng"], "precision": "country"}

    # Step F: Fallback to full string clean match as a last resort
    full_clean = clean_string(location_text)
    if full_clean in _CITY_INDEX:
        best = _CITY_INDEX[full_clean][0]
        return {"lat": best["lat"], "lng": best["lng"], "precision": "city"}
    if full_clean in _REGION_INDEX:
        r = _REGION_INDEX[full_clean]
        return {"lat": r["lat"], "lng": r["lng"], "precision": "region"}
    if full_clean in _COUNTRY_INDEX:
        c = _COUNTRY_INDEX[full_clean]
        return {"lat": c["lat"], "lng": c["lng"], "precision": "country"}

    return None
