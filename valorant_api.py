import os
import json
import httpx
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
from config import CATALOG_CACHE_FILE, IMAGES_CACHE_DIR

API_BASE = "https://valorant-api.com/v1"

# In-memory cached catalog
_CATALOG_CACHE: Optional[Dict[str, Any]] = None
_UUID_TO_SKIN: Dict[str, Dict[str, Any]] = {}
_LEVEL_TO_SKIN_UUID: Dict[str, str] = {}

WEAPON_TRANSLATIONS = {
    "Vandal": "Вандал (Vandal)",
    "Phantom": "Фантом (Phantom)",
    "Operator": "Оператор (Operator)",
    "Sheriff": "Шериф (Sheriff)",
    "Ghost": "Призрак (Ghost)",
    "Classic": "Классик (Classic)",
    "Spectre": "Спектр (Spectre)",
    "Melee": "Холодное оружие / Нож (Melee)",
    "Guardian": "Страж (Guardian)",
    "Marshal": "Маршал (Marshal)",
    "Outlaw": "Аутло (Outlaw)",
    "Bulldog": "Бульдог (Bulldog)",
    "Ares": "Арес (Ares)",
    "Odin": "Один (Odin)",
    "Judge": "Судья (Judge)",
    "Bucky": "Баки (Bucky)",
    "Frenzy": "Френзи (Frenzy)",
    "Shorty": "Шорти (Shorty)",
    "Stinger": "Стингер (Stinger)",
}

def _build_indexes(catalog: Dict[str, Any]):
    global _UUID_TO_SKIN, _LEVEL_TO_SKIN_UUID
    _UUID_TO_SKIN = {}
    _LEVEL_TO_SKIN_UUID = {}

    for skin in catalog.get("skins", []):
        uuid = skin["uuid"]
        _UUID_TO_SKIN[uuid] = skin
        for lvl_uuid in skin.get("level_uuids", []):
            _LEVEL_TO_SKIN_UUID[lvl_uuid] = uuid

def fetch_catalog_from_api() -> Dict[str, Any]:
    """Fetches full weapon & skin data in both Russian and English from valorant-api.com."""
    with httpx.Client(timeout=15.0) as client:
        res_ru = client.get(f"{API_BASE}/weapons?language=ru-RU")
        res_ru.raise_for_status()
        weapons_ru = res_ru.json().get("data", [])

        res_en = client.get(f"{API_BASE}/weapons?language=en-US")
        res_en.raise_for_status()
        weapons_en = res_en.json().get("data", [])

    # Map English skin names by skin uuid
    en_skins_map: Dict[str, Dict[str, Any]] = {}
    en_weapon_map: Dict[str, str] = {}

    for w in weapons_en:
        en_weapon_name = w.get("displayName", "")
        for s in w.get("skins", []):
            en_skins_map[s["uuid"]] = {
                "name": s.get("displayName", ""),
                "weapon": en_weapon_name
            }

    parsed_skins: List[Dict[str, Any]] = []
    weapons_list: List[str] = []

    for w in weapons_ru:
        w_uuid = w.get("uuid", "")
        # Weapon name in EN and RU
        w_name_en = w.get("displayName", "")
        # If RU weapon display name is something else, check en map
        if w_uuid in en_weapon_map:
            w_name_en = en_weapon_map[w_uuid]

        w_label = WEAPON_TRANSLATIONS.get(w_name_en, w_name_en)
        if w_label not in weapons_list and w_name_en != "Bandit" and w_name_en != "Warden":
            weapons_list.append(w_label)

        for s in w.get("skins", []):
            name_ru = s.get("displayName", "")
            en_info = en_skins_map.get(s["uuid"], {})
            name_en = en_info.get("name", name_ru)
            weapon_en = en_info.get("weapon", w_name_en)

            # Skip standard default skins (e.g. "Standard Vandal")
            if "standard" in name_en.lower() or "стандартн" in name_ru.lower():
                continue

            # Skip Random Favorite skins
            if "random" in name_en.lower() or "случайный" in name_ru.lower():
                continue

            # Find display icon
            icon_url = s.get("displayIcon")
            level_uuids = []
            for lvl in s.get("levels", []):
                lvl_id = lvl.get("uuid")
                if lvl_id:
                    level_uuids.append(lvl_id)
                if not icon_url and lvl.get("displayIcon"):
                    icon_url = lvl.get("displayIcon")

            if not icon_url and s.get("chromas"):
                for ch in s["chromas"]:
                    if ch.get("displayIcon"):
                        icon_url = ch.get("displayIcon")
                        break
                    elif ch.get("fullRender"):
                        icon_url = ch.get("fullRender")
                        break

            # If still no icon, skip
            if not icon_url:
                continue

            skin_obj = {
                "uuid": s["uuid"],
                "name_ru": name_ru,
                "name_en": name_en,
                "weapon_en": weapon_en,
                "weapon_label": WEAPON_TRANSLATIONS.get(weapon_en, weapon_en),
                "icon_url": icon_url,
                "level_uuids": level_uuids,
                "tier_uuid": s.get("contentTierUuid")
            }
            parsed_skins.append(skin_obj)

    # Sort alphabetically by Russian name
    parsed_skins.sort(key=lambda x: x["name_ru"])

    catalog_data = {
        "version": 1,
        "weapons": sorted(weapons_list),
        "skins": parsed_skins
    }

    # Save to cache
    try:
        with open(CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save catalog cache: {e}")

    return catalog_data

def load_or_fetch_catalog(force_refresh: bool = False) -> Dict[str, Any]:
    """Loads catalog from cache or fetches from API if not cached."""
    global _CATALOG_CACHE
    if not force_refresh and _CATALOG_CACHE:
        return _CATALOG_CACHE

    if not force_refresh and os.path.exists(CATALOG_CACHE_FILE):
        try:
            with open(CATALOG_CACHE_FILE, "r", encoding="utf-8") as f:
                _CATALOG_CACHE = json.load(f)
                _build_indexes(_CATALOG_CACHE)
                return _CATALOG_CACHE
        except Exception:
            pass

    _CATALOG_CACHE = fetch_catalog_from_api()
    _build_indexes(_CATALOG_CACHE)
    return _CATALOG_CACHE

def get_skin_by_uuid(uuid_or_level: str) -> Optional[Dict[str, Any]]:
    """Resolves any skin or skin-level UUID to its parent skin object."""
    if not _UUID_TO_SKIN:
        load_or_fetch_catalog()

    if uuid_or_level in _UUID_TO_SKIN:
        return _UUID_TO_SKIN[uuid_or_level]

    parent_uuid = _LEVEL_TO_SKIN_UUID.get(uuid_or_level)
    if parent_uuid and parent_uuid in _UUID_TO_SKIN:
        return _UUID_TO_SKIN[parent_uuid]

    return None

def search_skins(
    query: str = "",
    weapon_filter: str = "Все",
    only_wishlist: bool = False,
    wishlist_set: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """Filters skins by search query (RU or EN), weapon category, and wishlist."""
    catalog = load_or_fetch_catalog()
    skins = catalog.get("skins", [])
    query = query.strip().lower()

    results = []
    for s in skins:
        # Wishlist filter
        if only_wishlist:
            if not wishlist_set or s["uuid"] not in wishlist_set:
                continue

        # Weapon filter
        if weapon_filter and weapon_filter != "Все":
            if s["weapon_label"] != weapon_filter and s["weapon_en"] != weapon_filter:
                continue

        # Search query filter (matches Russian or English name)
        if query:
            match_ru = query in s["name_ru"].lower()
            match_en = query in s["name_en"].lower()
            match_wp = query in s["weapon_label"].lower() or query in s["weapon_en"].lower()
            if not (match_ru or match_en or match_wp):
                continue

        results.append(s)

    return results

def get_cached_image_path(skin_uuid: str) -> Path:
    return IMAGES_CACHE_DIR / f"{skin_uuid}.png"

def download_skin_image(skin_uuid: str, icon_url: str) -> Optional[str]:
    """Downloads skin thumbnail into cache if not present."""
    file_path = get_cached_image_path(skin_uuid)
    if file_path.exists() and file_path.stat().st_size > 0:
        return str(file_path)

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(icon_url)
            if resp.status_code == 200:
                with open(file_path, "wb") as f:
                    f.write(resp.content)
                return str(file_path)
    except Exception as e:
        print(f"Failed to download image for {skin_uuid}: {e}")

    return None
