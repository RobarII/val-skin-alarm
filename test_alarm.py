import os
import unittest
from storage import (
    save_profile,
    load_profile,
    clear_profile,
    save_wishlist,
    load_wishlist,
    toggle_wishlist_item,
    save_shop_cache,
    load_shop_cache,
    is_shop_expired
)
from valorant_api import load_or_fetch_catalog, search_skins, get_skin_by_uuid
from riot_client import generate_demo_storefront

class TestValorantAlarm(unittest.TestCase):
    def setUp(self):
        self.orig_profile = load_profile()
        clear_profile()

    def tearDown(self):
        clear_profile()
        if self.orig_profile:
            save_profile(
                self.orig_profile.get("game_name", ""),
                self.orig_profile.get("tag_line", ""),
                self.orig_profile.get("puuid", ""),
                self.orig_profile.get("region", "eu"),
                self.orig_profile.get("autostart", False)
            )

    def test_profile_storage(self):
        profile = save_profile("TenZ", "0000", "test-puuid", "eu", False)
        self.assertIsNotNone(profile)
        loaded = load_profile()
        self.assertEqual(loaded["game_name"], "TenZ")
        self.assertEqual(loaded["tag_line"], "0000")
        self.assertEqual(loaded["puuid"], "test-puuid")

    def test_wishlist_toggle(self):
        test_uuid = "e5490f71-455b-74ad-f762-f5a876d4dff9"
        # Initially not in wishlist
        if test_uuid in load_wishlist():
            toggle_wishlist_item(test_uuid)

        added = toggle_wishlist_item(test_uuid)
        self.assertTrue(added)
        self.assertIn(test_uuid, load_wishlist())

        removed = toggle_wishlist_item(test_uuid)
        self.assertFalse(removed)
        self.assertNotIn(test_uuid, load_wishlist())

    def test_catalog_search(self):
        catalog = load_or_fetch_catalog()
        self.assertGreater(len(catalog["skins"]), 1000)

        # Search in Russian
        ru_results = search_skins(query="Жнец")
        self.assertGreater(len(ru_results), 0)

        # Search in English
        en_results = search_skins(query="Prime")
        self.assertGreater(len(en_results), 0)

        # Weapon filter
        vandal_results = search_skins(weapon_filter="Вандал (Vandal)")
        self.assertGreater(len(vandal_results), 50)

    def test_demo_storefront_generation(self):
        demo = generate_demo_storefront()
        self.assertEqual(len(demo["skins"]), 4)
        for s_uuid in demo["skins"]:
            skin = get_skin_by_uuid(s_uuid)
            self.assertIsNotNone(skin)

    def test_shop_expiration(self):
        # Empty cache is expired
        self.assertTrue(is_shop_expired({}))

        # Future expires_at is not expired
        import time
        valid_cache = {
            "skins": ["1", "2", "3", "4"],
            "expires_at": time.time() + 3600,
            "last_updated": time.time()
        }
        self.assertFalse(is_shop_expired(valid_cache))

        # Past expires_at is expired
        expired_cache = {
            "skins": ["1", "2", "3", "4"],
            "expires_at": time.time() - 100,
            "last_updated": time.time() - 3600
        }
        self.assertTrue(is_shop_expired(expired_cache))

if __name__ == "__main__":
    unittest.main()
