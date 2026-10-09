import threading
from typing import List, Optional, Dict, Any, Set
from pathlib import Path
from PIL import Image

import customtkinter as ctk

from storage import load_wishlist, toggle_wishlist_item, is_in_wishlist
from valorant_api import (
    load_or_fetch_catalog,
    search_skins,
    download_skin_image,
    get_cached_image_path,
    WEAPON_TRANSLATIONS
)

ITEMS_PER_PAGE = 24

class CatalogCard(ctk.CTkFrame):
    def __init__(self, master, skin_data: Dict[str, Any], is_wishlist: bool, on_toggle_callback, **kwargs):
        border_width = 2 if is_wishlist else 1
        border_color = ("#FD4556", "#FD4556") if is_wishlist else ("gray85", "#27272a")
        card_fg = ("white", "#18181b") if not is_wishlist else ("#FFF8F8", "#1e1315")

        super().__init__(
            master,
            corner_radius=10,
            border_width=border_width,
            border_color=border_color,
            fg_color=card_fg,
            **kwargs
        )
        self.skin_data = skin_data
        self.is_wishlist = is_wishlist
        self.on_toggle_callback = on_toggle_callback
        self.skin_uuid = skin_data["uuid"]

        self._build_ui()

    def _build_ui(self):
        # Weapon category label
        wp_text = self.skin_data.get("weapon_label", "")
        self.wp_label = ctk.CTkLabel(
            self,
            text=wp_text.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("gray50", "gray50")
        )
        self.wp_label.pack(padx=10, pady=(8, 1), anchor="w")

        # Name RU
        name_ru = self.skin_data.get("name_ru", "")
        self.name_label = ctk.CTkLabel(
            self,
            text=name_ru,
            font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=190,
            justify="left"
        )
        self.name_label.pack(padx=10, pady=(0, 1), anchor="w")

        # Name EN
        name_en = self.skin_data.get("name_en", "")
        if name_en and name_en != name_ru:
            self.en_label = ctk.CTkLabel(
                self,
                text=name_en,
                font=ctk.CTkFont(size=10),
                text_color=("gray45", "gray55"),
                wraplength=190,
                justify="left"
            )
            self.en_label.pack(padx=10, pady=(0, 4), anchor="w")

        # Image thumbnail
        self.img_label = ctk.CTkLabel(self, text="...", height=70)
        self.img_label.pack(padx=10, pady=(2, 6), fill="x")

        # Wishlist button
        btn_text = "★ В вишлисте" if self.is_wishlist else "☆ Отслеживать"
        btn_fg = ("#FD4556", "#FD4556") if self.is_wishlist else ("gray85", "#27272a")
        btn_hover = ("#E03E4D", "#E03E4D") if self.is_wishlist else ("gray75", "#3f3f46")
        btn_text_color = "white" if self.is_wishlist else ("black", "white")

        self.btn = ctk.CTkButton(
            self,
            text=btn_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            corner_radius=6,
            fg_color=btn_fg,
            hover_color=btn_hover,
            text_color=btn_text_color,
            command=self._handle_click
        )
        self.btn.pack(padx=10, pady=(0, 10), fill="x")

        self._load_image_async()

    def _handle_click(self):
        new_state = self.on_toggle_callback(self.skin_uuid)
        self.is_wishlist = new_state
        if new_state:
            self.btn.configure(text="★ В вишлисте", fg_color="#FD4556", hover_color="#E03E4D", text_color="white")
            self.configure(border_color=("#FD4556", "#FD4556"), border_width=2, fg_color=("#FFF8F8", "#1e1315"))
        else:
            self.btn.configure(text="☆ Отслеживать", fg_color=("gray85", "#27272a"), hover_color=("gray75", "#3f3f46"), text_color=("black", "white"))
            self.configure(border_color=("gray85", "#27272a"), border_width=1, fg_color=("white", "#18181b"))

    def _load_image_async(self):
        threading.Thread(target=self._fetch_and_render, daemon=True).start()

    def _fetch_and_render(self):
        icon_url = self.skin_data.get("icon_url")
        if not icon_url:
            return

        cached_path = download_skin_image(self.skin_uuid, icon_url)
        if cached_path and Path(cached_path).exists():
            try:
                pil_img = Image.open(cached_path)
                width, height = pil_img.size
                target_w = 180
                target_h = max(20, int((target_w / width) * height))
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
                self.after(0, lambda: self.img_label.configure(image=ctk_img, text=""))
            except Exception:
                self.after(0, lambda: self.img_label.configure(text="[Скин]"))


class CatalogTab(ctk.CTkFrame):
    def __init__(self, master, on_wishlist_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_wishlist_change = on_wishlist_change
        self.current_page = 1
        self.filtered_skins: List[Dict[str, Any]] = []
        self._search_debounce_timer = None

        self._build_ui()
        self.after(100, self._initial_load)

    def _build_ui(self):
        # Top Controls Frame
        self.controls_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#18181b"))
        self.controls_frame.pack(fill="x", padx=15, pady=(15, 8))

        # Row 1: Search & Filter
        self.row1 = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.row1.pack(fill="x", padx=14, pady=(12, 6))

        # Search Box
        self.search_entry = ctk.CTkEntry(
            self.row1,
            placeholder_text="🔍 Поиск по названию на русском или английском (Прайм, Reaver, Вандал...)",
            height=38,
            corner_radius=8
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        # Weapon Category Menu
        catalog = load_or_fetch_catalog()
        weapons = ["Все виды оружия"] + catalog.get("weapons", [])
        self.weapon_var = ctk.StringVar(value="Все виды оружия")
        self.weapon_menu = ctk.CTkOptionMenu(
            self.row1,
            values=weapons,
            variable=self.weapon_var,
            width=220,
            height=38,
            corner_radius=8,
            command=lambda _: self._apply_filter(reset_page=True)
        )
        self.weapon_menu.pack(side="left", padx=(0, 10))

        # Only Wishlist switch
        self.only_wishlist_var = ctk.BooleanVar(value=False)
        self.only_wishlist_switch = ctk.CTkSwitch(
            self.row1,
            text="⭐ Только вишлист",
            variable=self.only_wishlist_var,
            command=lambda: self._apply_filter(reset_page=True),
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.only_wishlist_switch.pack(side="left")

        # Row 2: Status & Pagination info
        self.row2 = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.row2.pack(fill="x", padx=14, pady=(0, 10))

        self.count_label = ctk.CTkLabel(
            self.row2,
            text="Загрузка скинов...",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray50")
        )
        self.count_label.pack(side="left")

        # Pagination Buttons
        self.page_frame = ctk.CTkFrame(self.row2, fg_color="transparent")
        self.page_frame.pack(side="right")

        self.prev_btn = ctk.CTkButton(
            self.page_frame,
            text="◀ Назад",
            width=70,
            height=28,
            corner_radius=6,
            command=self._prev_page
        )
        self.prev_btn.pack(side="left", padx=4)

        self.page_label = ctk.CTkLabel(
            self.page_frame,
            text="Стр. 1 из 1",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.page_label.pack(side="left", padx=8)

        self.next_btn = ctk.CTkButton(
            self.page_frame,
            text="Вперед ▶",
            width=70,
            height=28,
            corner_radius=6,
            command=self._next_page
        )
        self.next_btn.pack(side="left", padx=4)

        # Center Scrollable Grid for Cards
        self.cards_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.cards_scroll.pack(fill="both", expand=True, padx=15, pady=4)

        self.cards_grid = ctk.CTkFrame(self.cards_scroll, fg_color="transparent")
        self.cards_grid.pack(fill="both", expand=True)

        for col in range(4):
            self.cards_grid.columnconfigure(col, weight=1, minsize=200)

    def _initial_load(self):
        self._apply_filter(reset_page=True)

    def _on_search_key(self, event):
        if self._search_debounce_timer:
            self.after_cancel(self._search_debounce_timer)
        self._search_debounce_timer = self.after(250, lambda: self._apply_filter(reset_page=True))

    def _apply_filter(self, reset_page: bool = False):
        if reset_page:
            self.current_page = 1

        query = self.search_entry.get().strip()
        weapon_sel = self.weapon_var.get()
        weapon_filter = "Все" if weapon_sel == "Все виды оружия" else weapon_sel
        only_wish = self.only_wishlist_var.get()
        wishlist_set = load_wishlist()

        self.filtered_skins = search_skins(
            query=query,
            weapon_filter=weapon_filter,
            only_wishlist=only_wish,
            wishlist_set=wishlist_set
        )

        total_count = len(self.filtered_skins)
        total_pages = max(1, (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

        if self.current_page > total_pages:
            self.current_page = total_pages

        self.count_label.configure(text=f"Найдено скинов: {total_count} (в вишлисте: {len(wishlist_set)})")
        self.page_label.configure(text=f"Стр. {self.current_page} из {total_pages}")

        self.prev_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.next_btn.configure(state="normal" if self.current_page < total_pages else "disabled")

        self._render_current_page(wishlist_set)

    def _render_current_page(self, wishlist_set: Set[str]):
        # Clear grid
        for child in self.cards_grid.winfo_children():
            child.destroy()

        start_idx = (self.current_page - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_items = self.filtered_skins[start_idx:end_idx]

        if not page_items:
            empty_msg = ctk.CTkLabel(
                self.cards_grid,
                text="Скины по данному запросу не найдены.",
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray50")
            )
            empty_msg.grid(row=0, column=0, columnspan=4, pady=60)
            return

        row = 0
        col = 0
        for skin in page_items:
            is_wish = skin["uuid"] in wishlist_set
            card = CatalogCard(
                self.cards_grid,
                skin_data=skin,
                is_wishlist=is_wish,
                on_toggle_callback=self._on_card_toggle
            )
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _on_card_toggle(self, skin_uuid: str) -> bool:
        new_state = toggle_wishlist_item(skin_uuid)
        wishlist_set = load_wishlist()
        self.count_label.configure(text=f"Найдено скинов: {len(self.filtered_skins)} (в вишлисте: {len(wishlist_set)})")
        if self.on_wishlist_change:
            self.on_wishlist_change(skin_uuid, new_state)

        # If filtered by wishlist only, refresh view
        if self.only_wishlist_var.get():
            self._apply_filter(reset_page=False)

        return new_state

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._apply_filter(reset_page=False)
            self.cards_scroll._parent_canvas.yview_moveto(0)

    def _next_page(self):
        total_pages = max(1, (len(self.filtered_skins) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        if self.current_page < total_pages:
            self.current_page += 1
            self._apply_filter(reset_page=False)
            self.cards_scroll._parent_canvas.yview_moveto(0)
