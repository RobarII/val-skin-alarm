import os
import customtkinter as ctk
from typing import Optional, Dict, Any

from config import APP_NAME, APP_VERSION
from storage import load_profile, clear_profile
from autostart import is_autostart_enabled, set_autostart
from ui.registration import RegistrationFrame
from ui.shop_tab import ShopTab
from ui.catalog_tab import CatalogTab

class ValorantAlarmApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window settings
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1100x750")
        self.minsize(960, 640)

        # System theme (adapts to Windows Light/Dark theme automatically)
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("dark-blue")

        self.profile: Optional[Dict[str, Any]] = load_profile()

        # Main container
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self._show_appropriate_view()

    def _show_appropriate_view(self):
        # Clear container
        for widget in self.container.winfo_children():
            widget.destroy()

        if not self.profile:
            self._show_registration_view()
        else:
            self._show_main_dashboard()

    def _show_registration_view(self):
        self.reg_frame = RegistrationFrame(
            self.container,
            on_success=self._on_registration_success
        )

    def _on_registration_success(self, profile: Dict[str, Any]):
        self.profile = profile
        self._show_main_dashboard()

    def _show_main_dashboard(self):
        for widget in self.container.winfo_children():
            widget.destroy()

        # Top Bar
        self.top_bar = ctk.CTkFrame(self.container, corner_radius=0, height=54, fg_color=("gray95", "#121214"))
        self.top_bar.pack(fill="x", side="top")

        # Brand / Title
        brand_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        brand_frame.pack(side="left", padx=16, pady=8)

        title_lbl = ctk.CTkLabel(
            brand_frame,
            text="🎯 VALORANT SKIN ALARM",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("#FD4556", "#FD4556")
        )
        title_lbl.pack(side="left")

        # User Info Badge
        name = self.profile.get("game_name", "Игрок")
        tag = self.profile.get("tag_line", "0000")
        region = self.profile.get("region", "eu").upper()

        user_badge = ctk.CTkLabel(
            self.top_bar,
            text=f"👤 {name}#{tag}  [{region}]",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray85", "#27272a"),
            corner_radius=6,
            height=28,
            padx=10
        )
        user_badge.pack(side="left", padx=12, pady=12)

        # Right Controls: Autostart, Theme, Logout
        right_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        right_frame.pack(side="right", padx=16, pady=8)

        # Autostart switch
        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.autostart_switch = ctk.CTkSwitch(
            right_frame,
            text="Демон при старте Windows",
            variable=self.autostart_var,
            command=self._toggle_autostart,
            font=ctk.CTkFont(size=11)
        )
        self.autostart_switch.pack(side="left", padx=8)

        # Theme selector
        self.theme_menu = ctk.CTkOptionMenu(
            right_frame,
            values=["Системная", "Темная", "Светлая"],
            command=self._change_theme,
            width=110,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11)
        )
        self.theme_menu.pack(side="left", padx=6)

        # Logout / Switch profile button
        logout_btn = ctk.CTkButton(
            right_frame,
            text="Сменить аккаунт",
            width=110,
            height=28,
            corner_radius=6,
            fg_color=("gray80", "#27272a"),
            hover_color=("gray70", "#3f3f46"),
            text_color=("black", "white"),
            font=ctk.CTkFont(size=11),
            command=self._logout
        )
        logout_btn.pack(side="left", padx=6)

        # Main Tabs
        self.tabview = ctk.CTkTabview(self.container, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        tab_shop = self.tabview.add("🛒 Ассортимент магазина")
        tab_catalog = self.tabview.add("📖 Каталог скинов")

        # Populate Tabs
        self.shop_view = ShopTab(tab_shop, profile=self.profile)
        self.shop_view.pack(fill="both", expand=True)

        self.catalog_view = CatalogTab(tab_catalog, on_wishlist_change=self._on_wishlist_changed)
        self.catalog_view.pack(fill="both", expand=True)

    def _on_wishlist_changed(self, skin_uuid: str, is_in_wish: bool):
        # Refresh shop cards wishlist highlighting if visible
        if hasattr(self, "shop_view") and self.shop_view:
            for card in self.shop_view.cards:
                if card.skin_uuid == skin_uuid:
                    if is_in_wish:
                        card.is_wishlist = True
                        card.fav_btn.configure(text="★ В вишлисте", fg_color="#FD4556", hover_color="#E03E4D", text_color="white")
                        card.configure(border_color=("#FD4556", "#FD4556"), border_width=2)
                    else:
                        card.is_wishlist = False
                        card.fav_btn.configure(text="☆ В вишлист", fg_color=("gray85", "#27272a"), hover_color=("gray75", "#3f3f46"), text_color=("black", "white"))
                        card.configure(border_color=("gray80", "#27272a"), border_width=1)

    def _toggle_autostart(self):
        new_val = self.autostart_var.get()
        set_autostart(new_val)

    def _change_theme(self, choice: str):
        if choice == "Темная":
            ctk.set_appearance_mode("dark")
        elif choice == "Светлая":
            ctk.set_appearance_mode("light")
        else:
            ctk.set_appearance_mode("system")

    def _logout(self):
        clear_profile()
        self.profile = None
        self._show_appropriate_view()
