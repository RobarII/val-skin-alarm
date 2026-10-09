import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Set, Any
from config import PROFILE_FILE, WISHLIST_FILE, SHOP_CACHE_FILE, STORE_RESET_HOUR

def _read_json(filepath) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _write_json(filepath, data: Any):
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, filepath)

# --- PROFILE STORAGE ---

def load_profile() -> Optional[Dict[str, Any]]:
    data = _read_json(PROFILE_FILE)
    if data and data.get("game_name") and data.get("tag_line"):
        return data
    return None

def save_profile(game_name: str, tag_line: str, puuid: str = "", region: str = "eu", autostart: bool = False):
    profile = {
        "game_name": game_name.strip(),
        "tag_line": tag_line.strip().lstrip("#"),
        "puuid": puuid.strip(),
        "region": region.strip().lower(),
        "autostart": autostart,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    _write_json(PROFILE_FILE, profile)
    return profile

def clear_profile():
    if os.path.exists(PROFILE_FILE):
        try:
            os.remove(PROFILE_FILE)
        except Exception:
            pass

# --- WISHLIST STORAGE ---

def load_wishlist() -> Set[str]:
    data = _read_json(WISHLIST_FILE)
    if isinstance(data, dict):
        return set(data.get("skin_uuids", []))
    if isinstance(data, list):
        return set(data)
    return set()

def save_wishlist(skin_uuids: Set[str] or List[str]):
    _write_json(WISHLIST_FILE, {
        "skin_uuids": sorted(list(set(skin_uuids))),
        "updated_at": datetime.now(timezone.utc).isoformat()
    })

def toggle_wishlist_item(skin_uuid: str) -> bool:
    """Toggles wishlist status. Returns True if now in wishlist, False if removed."""
    current = load_wishlist()
    if skin_uuid in current:
        current.remove(skin_uuid)
        added = False
    else:
        current.add(skin_uuid)
        added = True
    save_wishlist(current)
    return added

def is_in_wishlist(skin_uuid: str) -> bool:
    return skin_uuid in load_wishlist()

# --- SHOP CACHE STORAGE ---

def load_shop_cache() -> Dict[str, Any]:
    return _read_json(SHOP_CACHE_FILE)

def save_shop_cache(skins: List[str], expires_at: Optional[float] = None, notified_today: bool = False, source: str = "riot_client"):
    cache = {
        "skins": skins,
        "expires_at": expires_at,
        "last_updated": datetime.now(timezone.utc).timestamp(),
        "notified_today": notified_today,
        "source": source
    }
    _write_json(SHOP_CACHE_FILE, cache)
    return cache

def mark_shop_notified():
    cache = load_shop_cache()
    if cache:
        cache["notified_today"] = True
        _write_json(SHOP_CACHE_FILE, cache)

def is_shop_expired(cache: Optional[Dict[str, Any]] = None) -> bool:
    """
    Checks if shop is expired based on exact expiration timestamp or daily reset cutoff.
    Store resets every 24 hours (default 06:00 local time / 00:00 UTC).
    """
    if cache is None:
        cache = load_shop_cache()

    if not cache or not cache.get("skins"):
        return True

    now = datetime.now()
    now_ts = datetime.now(timezone.utc).timestamp()

    # If Riot storefront provided exact expiration timestamp
    expires_at = cache.get("expires_at")
    if expires_at and isinstance(expires_at, (int, float)) and expires_at > 0:
        if now_ts >= expires_at:
            return True
        return False

    # Check based on daily cutoff (6:00 AM local time)
    last_updated_ts = cache.get("last_updated")
    if not last_updated_ts:
        return True

    last_updated_dt = datetime.fromtimestamp(last_updated_ts)

    # Determine the most recent cutoff point
    if now.hour >= STORE_RESET_HOUR:
        cutoff = now.replace(hour=STORE_RESET_HOUR, minute=0, second=0, microsecond=0)
    else:
        cutoff = (now - timedelta(days=1)).replace(hour=STORE_RESET_HOUR, minute=0, second=0, microsecond=0)

    # If last updated was before the recent cutoff, it's expired
    return last_updated_dt < cutoff
