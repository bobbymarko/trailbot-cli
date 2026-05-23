"""Trailbot API client — scrapes trailbot.com's Next.js data endpoints."""

import json
import math
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

BASE_URL = "https://trailbot.com"
CACHE_DIR = Path.home() / ".cache" / "trailbot"
BUILD_ID_CACHE = CACHE_DIR / "buildid.json"
TRAILS_CACHE = CACHE_DIR / "trails.json"
BUILD_ID_TTL = 3600      # 1 hour
TRAILS_CACHE_TTL = 3600  # 1 hour

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _get_build_id() -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if BUILD_ID_CACHE.exists():
        try:
            state = json.loads(BUILD_ID_CACHE.read_text())
            if time.time() - state.get("ts", 0) < BUILD_ID_TTL:
                return state["buildId"]
        except Exception:
            pass

    req = urllib.request.Request(f"{BASE_URL}/trails", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode()

    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        raise RuntimeError("Could not extract buildId from trailbot.com — site may have changed.")

    build_id = m.group(1)
    BUILD_ID_CACHE.write_text(json.dumps({"buildId": build_id, "ts": time.time()}))
    return build_id


def _data_url(path: str) -> str:
    return f"{BASE_URL}/_next/data/{_get_build_id()}/{path}.json"


def _fetch_with_retry(path: str) -> dict:
    try:
        return _get(_data_url(path))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            if BUILD_ID_CACHE.exists():
                BUILD_ID_CACHE.unlink()
            return _get(_data_url(path))
        raise


def _fetch_org(org_slug: str) -> list[dict]:
    """Fetch all trails for an org (includes status, lat, lon)."""
    try:
        data = _fetch_with_retry(f"trails/{org_slug}")
        return data.get("pageProps", {}).get("trails", [])
    except Exception:
        return []


def get_directory() -> list[dict]:
    """Lightweight trail directory — name, slug, org, state, city. No status or coords."""
    data = _fetch_with_retry("trails")
    return data.get("pageProps", {}).get("trails", [])


def sync_trails(progress_cb=None) -> list[dict]:
    """Fetch all trails with status + coordinates via org pages. Caches result."""
    directory = get_directory()
    org_slugs = list({t["organization"]["slug"] for t in directory})

    all_trails = []
    completed = 0

    def fetch_org(slug):
        return _fetch_org(slug)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch_org, slug): slug for slug in org_slugs}
        for future in as_completed(futures):
            trails = future.result()
            all_trails.extend(trails)
            completed += 1
            if progress_cb:
                progress_cb(completed, len(org_slugs))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TRAILS_CACHE.write_text(json.dumps({"ts": time.time(), "trails": all_trails}))
    return all_trails


def get_cached_trails(auto_sync=True) -> list[dict]:
    """Return cached trail list (with status + coords), syncing if stale."""
    if TRAILS_CACHE.exists():
        try:
            data = json.loads(TRAILS_CACHE.read_text())
            if time.time() - data.get("ts", 0) < TRAILS_CACHE_TTL:
                return data["trails"]
        except Exception:
            pass

    if not auto_sync:
        return []

    return sync_trails()


def find_trail(slug: str) -> Optional[dict]:
    """Find a trail in the directory by slug or name (partial match ok)."""
    directory = get_directory()
    slug_lower = slug.lower()
    exact = [t for t in directory if t.get("slug", "").lower() == slug_lower]
    if exact:
        return exact[0]
    fuzzy = [
        t for t in directory
        if slug_lower in t.get("slug", "").lower() or slug_lower in t.get("trailName", "").lower()
    ]
    return fuzzy[0] if fuzzy else None


def get_trail_status(org_slug: str, trail_slug: str) -> dict:
    data = _fetch_with_retry(f"trails/{org_slug}/{trail_slug}")
    return data.get("pageProps", {}).get("trail", {})


def search_trails(query: str, state: Optional[str] = None) -> list[dict]:
    query = query.lower()
    directory = get_directory()
    results = [
        t for t in directory
        if query in t.get("trailName", "").lower()
        or query in t.get("slug", "").lower()
        or query in (t.get("city") or "").lower()
        or query in t.get("organization", {}).get("name", "").lower()
    ]
    if state:
        results = [t for t in results if t.get("state", "").upper() == state.upper()]
    return results


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def trails_near(lat: float, lon: float, radius_miles: float = 75,
                state: Optional[str] = None, auto_sync=True) -> list[dict]:
    trails = get_cached_trails(auto_sync=auto_sync)
    results = []
    for t in trails:
        tlat = t.get("lat")
        tlon = t.get("long") or t.get("lon")
        if tlat is None or tlon is None:
            continue
        if state and t.get("state", "").upper() != state.upper():
            continue
        dist = _haversine_miles(lat, lon, tlat, tlon)
        if dist <= radius_miles:
            results.append({**t, "_dist_miles": round(dist, 1)})
    results.sort(key=lambda t: t["_dist_miles"])
    return results


def open_trails(state: Optional[str] = None) -> list[dict]:
    trails = get_cached_trails()
    results = [t for t in trails if t.get("trailStatus") == "Open"]
    if state:
        results = [t for t in results if t.get("state", "").upper() == state.upper()]
    return results
