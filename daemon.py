import sys
import time
from typing import List

from storage import (
    load_profile,
    load_wishlist,
    load_shop_cache,
    save_shop_cache,
    is_shop_expired,
    mark_shop_notified
)
from valorant_api import get_skin_by_uuid, load_or_fetch_catalog
from riot_client import fetch_live_storefront
from notifier import notify_wishlist_match

def run_daemon_check() -> int:
    """
    Runs a lightweight background check when started as a daemon on system boot.
    If shop is fresh and no matches -> silently exits.
    If shop needs refresh -> attempts refresh; if wishlist item found -> notifies and exits.
    """
    profile = load_profile()
    if not profile:
        # User not registered yet, nothing to check
        return 0

    wishlist = load_wishlist()
    cache = load_shop_cache()

    # Pre-load catalog in memory for lookups
    load_or_fetch_catalog()

    if not is_shop_expired(cache):
        # Store is fresh for today
        if not wishlist:
            return 0

        # Check if already notified today
        if cache.get("notified_today"):
            return 0

        # Check if any store skin matches wishlist
        shop_skins = cache.get("skins", [])
        matched_names: List[str] = []
        for s_uuid in shop_skins:
            if s_uuid in wishlist:
                skin_obj = get_skin_by_uuid(s_uuid)
                matched_names.append(skin_obj["name_ru"] if skin_obj else "Скин")

        if matched_names:
            notify_wishlist_match(matched_names)
            mark_shop_notified()
            # Give toast thread a moment to dispatch
            time.sleep(1)

        # Silent exit
        return 0

    # Store is expired, try to fetch new storefront
    region = profile.get("region", "eu")
    success, msg, store_data = fetch_live_storefront(region=region)

    if success and store_data:
        skins = store_data.get("skins", [])
        expires_at = store_data.get("expires_at")
        save_shop_cache(skins, expires_at=expires_at, notified_today=False, source="riot_client")

        # Check against wishlist
        matched_names = []
        for s_uuid in skins:
            if s_uuid in wishlist:
                skin_obj = get_skin_by_uuid(s_uuid)
                matched_names.append(skin_obj["name_ru"] if skin_obj else "Скин")

        if matched_names:
            notify_wishlist_match(matched_names)
            mark_shop_notified()
            time.sleep(1)

    # Exits cleanly
    return 0

if __name__ == "__main__":
    sys.exit(run_daemon_check())
