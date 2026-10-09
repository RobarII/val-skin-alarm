import os
import random
import time
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from config import RIOT_API_KEY, RIOT_REGION, reload_env
from storage import load_wishlist
from valorant_api import load_or_fetch_catalog, get_skin_by_uuid

# Shards to regional routing for Riot Account API
REGION_ROUTING = {
    "eu": "europe",
    "europe": "europe",
    "na": "americas",
    "americas": "americas",
    "latam": "americas",
    "br": "americas",
    "ap": "asia",
    "kr": "asia",
    "asia": "asia",
}

def resolve_puuid_via_riot_api(
    game_name: str,
    tag_line: str,
    region: str = "europe",
    api_key: Optional[str] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Queries official Riot Account API:
    GET https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
    Returns: (success, message, account_data)
    """
    key = api_key or RIOT_API_KEY
    if not key:
        return False, "API ключ не указан в файле .env (RIOT_API_KEY)", None

    routing = REGION_ROUTING.get(region.lower(), "europe")
    url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {
        "X-Riot-Token": key
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return True, "Аккаунт успешно подтвержден через Riot API", data
            elif resp.status_code == 401 or resp.status_code == 403:
                return False, f"Ошибка Riot API ({resp.status_code}): неверный или истекший API ключ", None
            elif resp.status_code == 404:
                return False, f"Игрок '{game_name}#{tag_line}' не найден в регионе {routing}", None
            elif resp.status_code == 429:
                return False, "Превышен лимит запросов Riot API (Rate limit)", None
            else:
                return False, f"Ошибка Riot API: HTTP {resp.status_code}", None
    except Exception as e:
        return False, f"Сетевая ошибка при запросе к Riot API: {e}", None

def is_riot_client_running() -> bool:
    """Checks if Riot Client lockfile exists on disk."""
    lockfile_path = os.path.join(
        os.getenv('LOCALAPPDATA', ''),
        r'Riot Games\Riot Client\Config\lockfile'
    )
    return os.path.exists(lockfile_path)

def fetch_live_storefront(region: str = "eu") -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Attempts to fetch the player's personal daily storefront via the local Riot Client session.
    Returns: (success, message, store_data)
    """
    if not is_riot_client_running():
        return False, "Riot Client не запущен. Для получения актуального магазина запустите Riot Client.", None

    try:
        import valclient
        import requests
        import urllib3
        urllib3.disable_warnings()

        client = valclient.Client(region=region)
        client.activate()

        raw_store = None
        # 1. Primary: POST /store/v3/storefront/{puuid} (Riot current storefront endpoint)
        try:
            resp = requests.post(
                f"https://pd.{client.shard}.a.pvp.net/store/v3/storefront/{client.puuid}",
                headers=client.headers,
                json={},
                timeout=10
            )
            if resp.status_code == 200:
                raw_store = resp.json()
        except Exception:
            pass

        # 2. Fallback: POST /storefront/v2/players/{puuid}
        if not raw_store:
            try:
                resp = requests.post(
                    f"https://pd.{client.shard}.a.pvp.net/storefront/v2/players/{client.puuid}",
                    headers=client.headers,
                    json={},
                    timeout=10
                )
                if resp.status_code == 200:
                    raw_store = resp.json()
            except Exception:
                pass

        # 3. Fallback: valclient default
        if not raw_store:
            try:
                raw_store = client.store_fetch_storefront()
            except Exception:
                pass

        if not raw_store:
            return False, "Не удалось получить данные магазина (сервер Riot не ответил или вернул ошибку).", None

        # SkinsPanelLayout contains the 4 daily offers
        panel = raw_store.get("SkinsPanelLayout", {})
        offers = panel.get("SingleItemOffers", [])
        duration = panel.get("SingleItemOffersRemainingDurationInSeconds", 86400)

        # Convert offers into our skin UUIDs
        resolved_skin_uuids = []
        for offer_id in offers:
            skin_obj = get_skin_by_uuid(offer_id)
            if skin_obj:
                resolved_skin_uuids.append(skin_obj["uuid"])
            else:
                resolved_skin_uuids.append(offer_id)

        now_ts = datetime.now(timezone.utc).timestamp()
        expires_at = now_ts + duration

        data = {
            "skins": resolved_skin_uuids,
            "duration_seconds": duration,
            "expires_at": expires_at,
            "source": "riot_client",
            "puuid": client.puuid,
            "player_name": client.player_name,
            "player_tag": client.player_tag
        }

        return True, "Магазин успешно обновлен через Riot Client!", data

    except Exception as e:
        return False, f"Не удалось подключиться к Riot Client: {e}", None

def generate_demo_storefront(include_wishlist_chance: bool = True) -> Dict[str, Any]:
    """
    Generates a demo 4-skin storefront for testing notifications and UI without the game running.
    """
    catalog = load_or_fetch_catalog()
    all_skins = catalog.get("skins", [])
    if not all_skins:
        return {"skins": [], "expires_at": None, "source": "demo"}

    wishlist = load_wishlist()
    selected_uuids = []

    # If wishlist has items and chance is enabled, include at least one wishlist skin to trigger alarm!
    if wishlist and include_wishlist_chance:
        wishlist_list = list(wishlist)
        random.shuffle(wishlist_list)
        for w_uuid in wishlist_list:
            if get_skin_by_uuid(w_uuid):
                selected_uuids.append(w_uuid)
                break

    # Pick random skins to make 4 total
    available_skins = [s["uuid"] for s in all_skins if s["uuid"] not in selected_uuids]
    random.shuffle(available_skins)

    while len(selected_uuids) < 4 and available_skins:
        selected_uuids.append(available_skins.pop())

    now_ts = datetime.now(timezone.utc).timestamp()
    # 24 hours expiry
    expires_at = now_ts + 86400

    return {
        "skins": selected_uuids,
        "expires_at": expires_at,
        "duration_seconds": 86400,
        "source": "demo"
    }
