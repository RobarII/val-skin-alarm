import threading
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from PIL import Image

import customtkinter as ctk

from config import STORE_RESET_HOUR
from storage import (
    load_shop_cache,
    save_shop_cache,
    is_shop_expired,
    load_wishlist,
    toggle_wishlist_item,
    mark_shop_notified
)
from valorant_api import get_skin_by_uuid, download_skin_image, get_cached_image_path
from riot_client import fetch_live_storefront, generate_demo_storefront
from notifier import notify_wishlist_match, send_test_notification

class ShopCard(ctk.CTkFrame):
    def __init__(self, master, skin_uuid: str, is_wishlist: bool, on_wishlist_toggle, **kwargs):
        border_width = 2 if is_wishlist else 1
        border_color = ("#FD4556", "#FD4556") if is_wishlist else ("gray80", "#27272a")
        card_fg = ("white", "#18181b") if not is_wishlist else ("#FFF5F5", "#221618")

        super().__init__(
            master,
            corner_radius=12,
            border_width=border_width,
            border_color=border_color,
            fg_color=card_fg,
            **kwargs
        )
        self.skin_uuid = skin_uuid
        self.is_wishlist = is_wishlist
        self.on_wishlist_toggle = on_wishlist_toggle

        self.skin_data = get_skin_by_uuid(skin_uuid)
        self._build_ui()

    def _build_ui(self):
        # Top banner for wishlist
        if self.is_wishlist:
            badge = ctk.CTkLabel(
                self,
                text="В ВАШЕМ ВИШЛИСТЕ",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#FD4556",
                text_color="white",
                corner_radius=6,
                height=22
            )
            badge.pack(padx=12, pady=(10, 0), anchor="w")

        # Weapon Label
        wp_text = self.skin_data.get("weapon_label", "Оружие") if self.skin_data else "Оружие"
        self.wp_label = ctk.CTkLabel(
            self,
            text=wp_text.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray50", "gray50")
        )
        self.wp_label.pack(padx=14, pady=(8 if self.is_wishlist else 12, 2), anchor="w")

        # Skin Name RU
        name_ru = self.skin_data.get("name_ru", "Неизвестный скин") if self.skin_data else "Неизвестный скин"
        self.name_label = ctk.CTkLabel(
            self,
            text=name_ru,
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=220,
            justify="left"
        )
        self.name_label.pack(padx=14, pady=(0, 2), anchor="w")

        # Skin Name EN
        name_en = self.skin_data.get("name_en", "") if self.skin_data else ""
        if name_en and name_en != name_ru:
            self.en_label = ctk.CTkLabel(
                self,
                text=name_en,
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray50"),
                wraplength=220,
                justify="left"
            )
            self.en_label.pack(padx=14, pady=(0, 6), anchor="w")

        # Image Container
        self.img_label = ctk.CTkLabel(self, text="Загрузка...", height=90)
        self.img_label.pack(padx=14, pady=(6, 12), fill="x")

        # Bottom Action / Wishlist Toggle
        btn_text = "В вишлисте" if self.is_wishlist else "В вишлист"
        btn_fg = ("#FD4556", "#FD4556") if self.is_wishlist else ("gray85", "#27272a")
        btn_hover = ("#E03E4D", "#E03E4D") if self.is_wishlist else ("gray75", "#3f3f46")
        btn_text_color = "white" if self.is_wishlist else ("black", "white")

        self.fav_btn = ctk.CTkButton(
            self,
            text=btn_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=30,
            corner_radius=6,
            fg_color=btn_fg,
            hover_color=btn_hover,
            text_color=btn_text_color,
            command=self._handle_toggle
        )
        self.fav_btn.pack(padx=14, pady=(0, 12), fill="x")

        # Start async image load
        self._load_image_async()

    def _handle_toggle(self):
        new_state = self.on_wishlist_toggle(self.skin_uuid)
        self.is_wishlist = new_state
        if new_state:
            self.fav_btn.configure(text="В вишлисте", fg_color="#FD4556", hover_color="#E03E4D", text_color="white")
            self.configure(border_color=("#FD4556", "#FD4556"), border_width=2)
        else:
            self.fav_btn.configure(text="В вишлист", fg_color=("gray85", "#27272a"), hover_color=("gray75", "#3f3f46"), text_color=("black", "white"))
            self.configure(border_color=("gray80", "#27272a"), border_width=1)

    def _load_image_async(self):
        threading.Thread(target=self._fetch_and_render_image, daemon=True).start()

    def _fetch_and_render_image(self):
        if not self.skin_data:
            return

        icon_url = self.skin_data.get("icon_url")
        if not icon_url:
            return

        cached_path = download_skin_image(self.skin_uuid, icon_url)
        if cached_path and Path(cached_path).exists():
            try:
                pil_img = Image.open(cached_path)
                # Resize keeping aspect ratio
                width, height = pil_img.size
                target_w = 210
                target_h = max(24, int((target_w / width) * height))
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
                self.after(0, lambda: self.img_label.configure(image=ctk_img, text=""))
            except Exception:
                self.after(0, lambda: self.img_label.configure(text="[Изображение]"))


class ShopTab(ctk.CTkFrame):
    def __init__(self, master, profile: Dict[str, Any], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.profile = profile
        self.cards: List[ShopCard] = []

        self._build_ui()
        self._start_countdown_loop()

        # Initial check
        self.after(200, self._initial_check)

    def _build_ui(self):
        # Top Header Bar
        self.header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#18181b"))
        self.header_frame.pack(fill="x", padx=15, pady=(15, 10))

        # Status text & countdown
        self.info_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.info_box.pack(side="left", padx=16, pady=12, fill="both", expand=True)

        self.status_label = ctk.CTkLabel(
            self.info_box,
            text="Проверка статуса магазина...",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.status_label.pack(fill="x")

        self.countdown_label = ctk.CTkLabel(
            self.info_box,
            text="До обновления: рассчитывается...",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray50"),
            anchor="w"
        )
        self.countdown_label.pack(fill="x", pady=(2, 0))

        # Action Buttons frame
        self.actions_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.actions_frame.pack(side="right", padx=16, pady=12)

        self.refresh_btn = ctk.CTkButton(
            self.actions_frame,
            text="Обновить",
            width=100,
            height=34,
            corner_radius=6,
            command=self._refresh_shop
        )
        self.refresh_btn.pack(side="left", padx=4)

        self.demo_btn = ctk.CTkButton(
            self.actions_frame,
            text="Демо-магазин",
            width=120,
            height=34,
            corner_radius=6,
            fg_color=("gray80", "#27272a"),
            hover_color=("gray70", "#3f3f46"),
            text_color=("black", "white"),
            command=self._generate_demo
        )
        self.demo_btn.pack(side="left", padx=4)

        self.test_toast_btn = ctk.CTkButton(
            self.actions_frame,
            text="Тест",
            width=70,
            height=34,
            corner_radius=6,
            fg_color=("gray80", "#27272a"),
            hover_color=("gray70", "#3f3f46"),
            text_color=("black", "white"),
            command=send_test_notification
        )
        self.test_toast_btn.pack(side="left", padx=4)

        # Center Container for 4 cards
        self.cards_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.cards_scroll.pack(fill="both", expand=True, padx=15, pady=5)

        self.cards_grid = ctk.CTkFrame(self.cards_scroll, fg_color="transparent")
        self.cards_grid.pack(expand=True, pady=10)

        # Configure 4 columns
        for c in range(4):
            self.cards_grid.columnconfigure(c, weight=1, minsize=240)

        self.empty_label = ctk.CTkLabel(
            self.cards_grid,
            text="Нажмите 'Обновить' или 'Демо-магазин' для отображения скинов.",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray50")
        )
        self.empty_label.grid(row=0, column=0, columnspan=4, pady=80)

    def _initial_check(self):
        cache = load_shop_cache()
        if cache and cache.get("skins") and not is_shop_expired(cache):
            self._render_skins(cache.get("skins", []), cache.get("source", "cache"))
            self._update_status(fresh=True, source=cache.get("source", "cache"))
        else:
            # Need refresh
            self._refresh_shop()

    def _update_status(self, fresh: bool, source: str = "cache", message: str = ""):
        if message:
            self.status_label.configure(text=message, text_color=("gray40", "gray60"))
            return

        if fresh:
            src_str = "Riot Client" if source == "riot_client" else ("Демо-режим" if source == "demo" else "Кэш")
            self.status_label.configure(
                text=f"Магазин актуален на сегодня ({src_str})",
                text_color=("#16a34a", "#22c55e")
            )
        else:
            self.status_label.configure(
                text="Требуется обновление ассортимента",
                text_color=("#d97706", "#f59e0b")
            )

    def _start_countdown_loop(self):
        self._update_countdown()

    def _update_countdown(self):
        cache = load_shop_cache()
        expires_at = cache.get("expires_at") if cache else None

        now = datetime.now()
        now_ts = datetime.now(timezone.utc).timestamp()

        if expires_at and expires_at > now_ts:
            diff = int(expires_at - now_ts)
        else:
            # Calculate time to 06:00
            if now.hour < STORE_RESET_HOUR:
                next_reset = now.replace(hour=STORE_RESET_HOUR, minute=0, second=0, microsecond=0)
            else:
                next_reset = (now + timedelta(days=1)).replace(hour=STORE_RESET_HOUR, minute=0, second=0, microsecond=0)
            diff = int((next_reset - now).total_seconds())

        hours = diff // 3600
        minutes = (diff % 3600) // 60
        seconds = diff % 60

        self.countdown_label.configure(
            text=f"До обновления магазина: {hours:02d}ч {minutes:02d}м {seconds:02d}с"
        )

        # Loop every second
        self.after(1000, self._update_countdown)

    def _refresh_shop(self):
        self.refresh_btn.configure(state="disabled", text="Обновление...")
        self._update_status(fresh=False, message="Запрос к Riot Client...")

        threading.Thread(target=self._do_refresh_thread, daemon=True).start()

    def _do_refresh_thread(self):
        region = self.profile.get("region", "eu")
        success, msg, store_data = fetch_live_storefront(region=region)

        if success and store_data:
            skins = store_data.get("skins", [])
            save_shop_cache(skins, expires_at=store_data.get("expires_at"), source="riot_client")
            self.after(0, lambda: self._on_refresh_success(skins, "riot_client"))
        else:
            # Riot client not open, fall back to cached shop or notify
            cache = load_shop_cache()
            if cache and cache.get("skins"):
                skins = cache.get("skins", [])
                self.after(0, lambda: self._on_refresh_fallback(skins, msg))
            else:
                self.after(0, lambda: self._on_refresh_failed(msg))

    def _on_refresh_success(self, skins: List[str], source: str):
        self.refresh_btn.configure(state="normal", text="Обновить")
        self._render_skins(skins, source)
        self._update_status(fresh=True, source=source)
        self._check_wishlist_matches(skins)

    def _on_refresh_fallback(self, skins: List[str], error_msg: str):
        self.refresh_btn.configure(state="normal", text="Обновить")
        self._render_skins(skins, "cache")
        self.status_label.configure(
            text=f"{error_msg} (Показан сохраненный кэш)",
            text_color=("gray40", "gray60")
        )

    def _on_refresh_failed(self, error_msg: str):
        self.refresh_btn.configure(state="normal", text="Обновить")
        self.status_label.configure(
            text=error_msg,
            text_color=("#dc2626", "#ef4444")
        )

    def _generate_demo(self):
        demo_store = generate_demo_storefront(include_wishlist_chance=True)
        skins = demo_store.get("skins", [])
        save_shop_cache(skins, expires_at=demo_store.get("expires_at"), source="demo")
        self._render_skins(skins, "demo")
        self._update_status(fresh=True, source="demo")
        self._check_wishlist_matches(skins)

    def _render_skins(self, skin_uuids: List[str], source: str):
        # Clear existing
        for widget in self.cards_grid.winfo_children():
            widget.destroy()

        wishlist = load_wishlist()
        self.cards = []

        col = 0
        for s_uuid in skin_uuids:
            is_wish = s_uuid in wishlist
            card = ShopCard(
                self.cards_grid,
                skin_uuid=s_uuid,
                is_wishlist=is_wish,
                on_wishlist_toggle=self._on_card_wishlist_toggle
            )
            card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
            self.cards.append(card)
            col += 1

    def _on_card_wishlist_toggle(self, skin_uuid: str) -> bool:
        new_state = toggle_wishlist_item(skin_uuid)
        # Notify user if added
        return new_state

    def _check_wishlist_matches(self, skins: List[str]):
        wishlist = load_wishlist()
        matched = []
        for s_uuid in skins:
            if s_uuid in wishlist:
                s_obj = get_skin_by_uuid(s_uuid)
                matched.append(s_obj["name_ru"] if s_obj else "Скин")

        if matched:
            notify_wishlist_match(matched)
            mark_shop_notified()
