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
        import threading
        threading.Thread(target=self._ensure_client_started, daemon=True).start()

    def _ensure_client_started(self):
        from riot_client import ensure_riot_client_running
        ensure_riot_client_running(timeout_seconds=20)

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
            text="VALORANT SKIN ALARM",
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
            text=f"{name}#{tag}  [{region}]",
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

        # Update banner button (hidden until update is detected)
        self.update_btn = ctk.CTkButton(
            right_frame,
            text="Обновление",
            width=120,
            height=28,
            corner_radius=6,
            fg_color="#16a34a",
            hover_color="#15803d",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_update_clicked
        )
        self.update_info = None

        # Settings button
        settings_btn = ctk.CTkButton(
            right_frame,
            text="Настройки",
            width=95,
            height=28,
            corner_radius=6,
            fg_color=("gray80", "#27272a"),
            hover_color=("gray70", "#3f3f46"),
            text_color=("black", "white"),
            font=ctk.CTkFont(size=11),
            command=self._open_settings_dialog
        )
        settings_btn.pack(side="left", padx=5)

        # Autostart switch
        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.autostart_switch = ctk.CTkSwitch(
            right_frame,
            text="Демон",
            variable=self.autostart_var,
            command=self._toggle_autostart,
            font=ctk.CTkFont(size=11)
        )
        self.autostart_switch.pack(side="left", padx=5)

        # Theme selector
        self.theme_menu = ctk.CTkOptionMenu(
            right_frame,
            values=["Системная", "Темная", "Светлая"],
            command=self._change_theme,
            width=100,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11)
        )
        self.theme_menu.pack(side="left", padx=5)

        # Logout / Switch profile button
        logout_btn = ctk.CTkButton(
            right_frame,
            text="Выйти",
            width=70,
            height=28,
            corner_radius=6,
            fg_color=("gray80", "#27272a"),
            hover_color=("gray70", "#3f3f46"),
            text_color=("black", "white"),
            font=ctk.CTkFont(size=11),
            command=self._logout
        )
        logout_btn.pack(side="left", padx=5)

        # Main Tabs
        self.tabview = ctk.CTkTabview(self.container, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        tab_shop = self.tabview.add("Ассортимент магазина")
        tab_catalog = self.tabview.add("Каталог скинов")

        # Populate Tabs
        self.shop_view = ShopTab(tab_shop, profile=self.profile)
        self.shop_view.pack(fill="both", expand=True)

        self.catalog_view = CatalogTab(tab_catalog, on_wishlist_change=self._on_wishlist_changed)
        self.catalog_view.pack(fill="both", expand=True)

        # Background update check
        self.after(1000, self._check_update_background)

    def _on_wishlist_changed(self, skin_uuid: str, is_in_wish: bool):
        # Refresh shop cards wishlist highlighting if visible
        if hasattr(self, "shop_view") and self.shop_view:
            for card in self.shop_view.cards:
                if card.skin_uuid == skin_uuid:
                    if is_in_wish:
                        card.is_wishlist = True
                        card.fav_btn.configure(text="В вишлисте", fg_color="#FD4556", hover_color="#E03E4D", text_color="white")
                        card.configure(border_color=("#FD4556", "#FD4556"), border_width=2)
                    else:
                        card.is_wishlist = False
                        card.fav_btn.configure(text="В вишлист", fg_color=("gray85", "#27272a"), hover_color=("gray75", "#3f3f46"), text_color=("black", "white"))
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

    def _check_update_background(self):
        import threading
        from updater import check_for_updates
        def worker():
            info = check_for_updates()
            if info:
                self.after(0, lambda: self._show_update_badge(info))
        threading.Thread(target=worker, daemon=True).start()

    def _show_update_badge(self, info: dict):
        self.update_info = info
        self.update_btn.configure(text=f"v{info.get('version', '')}")
        self.update_btn.pack(side="left", padx=5)

    def _on_update_clicked(self):
        if self.update_info:
            UpdateDialog(self, self.update_info)

    def _open_settings_dialog(self):
        SettingsDialog(self)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Настройки")
        self.geometry("480x400")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        from config import APP_VERSION
        from autostart import uninstall_daemon
        from updater import check_for_updates
        from riot_client import is_riot_client_running, ensure_riot_client_running

        # Frame
        frame = ctk.CTkFrame(self, corner_radius=12, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24, pady=20)

        # Title
        ctk.CTkLabel(frame, text="Настройки программы", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(0, 14))

        # Profile info
        profile = getattr(self.master, "profile", {}) or {}
        name = profile.get("game_name", "Игрок")
        tag = profile.get("tag_line", "0000")
        region = profile.get("region", "eu").upper()

        profile_box = ctk.CTkFrame(frame, fg_color=("gray85", "#27272a"), corner_radius=8)
        profile_box.pack(fill="x", pady=(0, 10), padx=0)
        ctk.CTkLabel(
            profile_box,
            text=f"Аккаунт: {name}#{tag}  (Регион: {region})",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(padx=12, pady=10, anchor="w")

        # Section 1: Riot Client status
        rc_row = ctk.CTkFrame(frame, fg_color="transparent")
        rc_row.pack(fill="x", pady=(4, 8))

        is_running = is_riot_client_running()
        status_text = "Riot Client: активен" if is_running else "Riot Client: не запущен"
        status_color = "#16a34a" if is_running else ("gray50", "gray50")

        self.rc_status_lbl = ctk.CTkLabel(rc_row, text=status_text, text_color=status_color, font=ctk.CTkFont(size=12, weight="bold"))
        self.rc_status_lbl.pack(side="left")

        def on_launch_rc():
            self.status_lbl.configure(text="Запуск Riot Client в трее...", text_color=("gray40", "gray60"))
            import threading
            def worker():
                ok, msg = ensure_riot_client_running(timeout_seconds=20)
                def finish():
                    if ok:
                        self.rc_status_lbl.configure(text="Riot Client: активен", text_color="#16a34a")
                        self.status_lbl.configure(text="Riot Client запущен в трее", text_color="#16a34a")
                    else:
                        self.status_lbl.configure(text=msg, text_color="#ef4444")
                self.after(0, finish)
            threading.Thread(target=worker, daemon=True).start()

        self.rc_btn = ctk.CTkButton(rc_row, text="Запустить в трее", height=30, width=150, corner_radius=6, command=on_launch_rc)
        self.rc_btn.pack(side="right")

        # Status label
        self.status_lbl = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=12))
        self.status_lbl.pack(fill="x", pady=(4, 6))

        ctk.CTkFrame(frame, height=1, fg_color=("gray80", "#27272a")).pack(fill="x", pady=6)

        # Section 2: Updates
        upd_row = ctk.CTkFrame(frame, fg_color="transparent")
        upd_row.pack(fill="x", pady=6)

        ctk.CTkLabel(upd_row, text=f"Версия программы: v{APP_VERSION}", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        def on_manual_check_update():
            self.status_lbl.configure(text="Проверка обновлений...", text_color=("gray40", "gray60"))
            import threading
            def check_thread():
                info = check_for_updates()
                if info:
                    self.after(0, lambda: UpdateDialog(self.master, info))
                    self.after(0, lambda: self.status_lbl.configure(text=f"Доступно обновление: {info['tag']}", text_color="#16a34a"))
                else:
                    self.after(0, lambda: self.status_lbl.configure(text="У вас установлена актуальная версия.", text_color=("gray40", "gray60")))
            threading.Thread(target=check_thread, daemon=True).start()

        check_upd_btn = ctk.CTkButton(upd_row, text="Проверить обновление", height=30, width=170, corner_radius=6, command=on_manual_check_update)
        check_upd_btn.pack(side="right")

        ctk.CTkFrame(frame, height=1, fg_color=("gray80", "#27272a")).pack(fill="x", pady=6)

        # Section 3: Uninstall daemon
        uninst_row = ctk.CTkFrame(frame, fg_color="transparent")
        uninst_row.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(uninst_row, text="Автозагрузка демона:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        def on_uninstall_daemon_click():
            success, msg = uninstall_daemon()
            if hasattr(self.master, "autostart_var"):
                self.master.autostart_var.set(False)
            self.status_lbl.configure(text=msg, text_color="#16a34a" if success else "#ef4444")

        uninst_btn = ctk.CTkButton(
            uninst_row,
            text="Удалить демона из реестра",
            height=30,
            width=210,
            corner_radius=6,
            fg_color=("#fee2e2", "#3b171a"),
            hover_color=("#fecaca", "#4c1d22"),
            text_color=("#dc2626", "#f87171"),
            command=on_uninstall_daemon_click
        )
        uninst_btn.pack(side="right")


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, update_info: dict):
        super().__init__(master)
        self.update_info = update_info
        self.title("Обновление ValSkinAlarm")
        self.geometry("480x360")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        frame = ctk.CTkFrame(self, corner_radius=12, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24, pady=20)

        # Title
        tag = self.update_info.get("tag", "новое")
        ctk.CTkLabel(frame, text=f"Доступно обновление {tag}", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(0, 6))

        # Notes scroll
        notes_box = ctk.CTkTextbox(frame, height=150, corner_radius=8)
        notes_box.pack(fill="both", expand=True, pady=(4, 12))
        notes_text = self.update_info.get("notes") or "Новые улучшения и исправления ошибок."
        notes_box.insert("1.0", notes_text)
        notes_box.configure(state="disabled")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(frame, height=10, corner_radius=5)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 6))

        self.status_lbl = ctk.CTkLabel(frame, text="Готово к загрузке", font=ctk.CTkFont(size=12), text_color=("gray40", "gray60"))
        self.status_lbl.pack(fill="x", pady=(0, 10))

        # Buttons
        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.pack(fill="x")

        self.start_btn = ctk.CTkButton(
            btns,
            text="Скачать и обновить",
            height=36,
            corner_radius=6,
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self._start_download
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        cancel_btn = ctk.CTkButton(
            btns,
            text="Отмена",
            height=36,
            corner_radius=6,
            fg_color=("gray80", "#27272a"),
            hover_color=("gray70", "#3f3f46"),
            text_color=("black", "white"),
            command=self.destroy
        )
        cancel_btn.pack(side="left", padx=(6, 0), width=100)

    def _start_download(self):
        self.start_btn.configure(state="disabled", text="Загрузка...")
        self.status_lbl.configure(text="Подключение к серверу...")

        import threading
        from updater import download_and_install_update

        def progress(pct, msg):
            self.after(0, lambda: self.progress_bar.set(pct))
            self.after(0, lambda: self.status_lbl.configure(text=msg))

        def worker():
            dl_url = self.update_info.get("download_url")
            html_url = self.update_info.get("html_url")
            success, msg = download_and_install_update(dl_url, html_url, progress_callback=progress)
            if not success:
                self.after(0, lambda: self.status_lbl.configure(text=msg, text_color="#ef4444"))
                self.after(0, lambda: self.start_btn.configure(state="normal", text="Повторить"))

        threading.Thread(target=worker, daemon=True).start()
