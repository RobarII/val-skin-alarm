import threading
import customtkinter as ctk
from typing import Callable, Optional, Dict, Any

from config import RIOT_API_KEY, reload_env
from storage import save_profile
from autostart import set_autostart, is_autostart_enabled
from riot_client import resolve_puuid_via_riot_api

class RegistrationFrame(ctk.CTkFrame):
    def __init__(self, master, on_success: Callable[[Dict[str, Any]], None], **kwargs):
        super().__init__(master, **kwargs)
        self.on_success = on_success

        self.pack(fill="both", expand=True, padx=20, pady=20)
        self._build_ui()

    def _build_ui(self):
        # Center card container
        self.card = ctk.CTkFrame(self, corner_radius=16, fg_color=("gray92", "#18181b"))
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # Header
        self.title_label = ctk.CTkLabel(
            self.card,
            text="VALORANT SKIN ALARM",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.title_label.pack(padx=40, pady=(35, 5))

        self.subtitle_label = ctk.CTkLabel(
            self.card,
            text="Локальная регистрация профиля",
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "gray60")
        )
        self.subtitle_label.pack(padx=40, pady=(0, 20))

        # Fields container
        self.form_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.form_frame.pack(padx=40, pady=10, fill="x")

        # Game Name Entry
        ctk.CTkLabel(self.form_frame, text="Ник в VALORANT:", anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", pady=(5, 2))
        self.name_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Например: TenZ", height=38, corner_radius=8)
        self.name_entry.pack(fill="x", pady=(0, 10))

        # TagLine Entry
        ctk.CTkLabel(self.form_frame, text="Тег (без #):", anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", pady=(5, 2))
        self.tag_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Например: 0000 или EUW", height=38, corner_radius=8)
        self.tag_entry.pack(fill="x", pady=(0, 10))

        # Region Selector
        ctk.CTkLabel(self.form_frame, text="Регион аккаунта:", anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", pady=(5, 2))
        self.region_var = ctk.StringVar(value="Europe (eu)")
        self.region_menu = ctk.CTkOptionMenu(
            self.form_frame,
            values=["Europe (eu)", "North America (na)", "Asia-Pacific (ap)", "Korea (kr)"],
            variable=self.region_var,
            height=38,
            corner_radius=8
        )
        self.region_menu.pack(fill="x", pady=(0, 10))

        # Riot API Key Entry (with .env auto-saving)
        reload_env()
        ctk.CTkLabel(self.form_frame, text="Riot API Ключ (опционально):", anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", pady=(5, 2))
        self.api_key_entry = ctk.CTkEntry(self.form_frame, placeholder_text="RGAPI-xxxx-xxxx-xxxx-xxxx", height=38, corner_radius=8)
        if RIOT_API_KEY:
            self.api_key_entry.insert(0, RIOT_API_KEY)
        self.api_key_entry.pack(fill="x", pady=(0, 6))

        # Helper buttons for .env and developer portal
        btn_row = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        from config import open_env_in_editor
        import webbrowser

        self.open_env_btn = ctk.CTkButton(
            btn_row,
            text="Открыть .env",
            width=110,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray85", "#27272a"),
            hover_color=("gray75", "#3f3f46"),
            text_color=("black", "white"),
            command=open_env_in_editor
        )
        self.open_env_btn.pack(side="left")

        self.get_key_btn = ctk.CTkButton(
            btn_row,
            text="Получить ключ Riot",
            width=140,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray85", "#27272a"),
            hover_color=("gray75", "#3f3f46"),
            text_color=("black", "white"),
            command=lambda: webbrowser.open("https://developer.riotgames.com/")
        )
        self.get_key_btn.pack(side="right")

        # Autostart switch
        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.autostart_switch = ctk.CTkSwitch(
            self.form_frame,
            text="Запускать как демон при старте Windows",
            variable=self.autostart_var,
            font=ctk.CTkFont(size=12)
        )
        self.autostart_switch.pack(anchor="w", pady=(0, 10))

        # Status / Feedback label
        has_key = bool(RIOT_API_KEY)
        key_status = "Riot API ключ загружен из .env" if has_key else "Ключ можно указать сейчас или использовать локальный режим"
        self.status_label = ctk.CTkLabel(
            self.form_frame,
            text=key_status,
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray50"),
            wraplength=340
        )
        self.status_label.pack(fill="x", pady=(0, 15))

        # Submit button
        self.submit_btn = ctk.CTkButton(
            self.card,
            text="Сохранить и продолжить",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            corner_radius=8,
            fg_color="#FD4556",
            hover_color="#E03E4D",
            command=self._on_submit
        )
        self.submit_btn.pack(padx=40, pady=(5, 35), fill="x")

    def _on_submit(self):
        name = self.name_entry.get().strip()
        tag = self.tag_entry.get().strip().lstrip("#")
        api_key = self.api_key_entry.get().strip()

        if not name or not tag:
            self.status_label.configure(
                text="Пожалуйста, введите ваш Ник и Тег",
                text_color="#FD4556"
            )
            return

        self.submit_btn.configure(state="disabled", text="Проверка...")
        self.status_label.configure(text="Подключение...", text_color=("gray40", "gray60"))

        threading.Thread(target=self._process_registration, args=(name, tag, api_key), daemon=True).start()

    def _process_registration(self, name: str, tag: str, api_key: str):
        reg_str = self.region_var.get()
        region_code = "eu"
        if "(na)" in reg_str:
            region_code = "na"
        elif "(ap)" in reg_str:
            region_code = "ap"
        elif "(kr)" in reg_str:
            region_code = "kr"

        # Save API key to .env if provided
        from config import save_api_key_to_env
        if api_key:
            save_api_key_to_env(api_key, region=region_code)
        reload_env()

        puuid = ""

        # Try official Riot API if key is available
        key_to_use = api_key or RIOT_API_KEY
        if key_to_use:
            success, msg, acc_data = resolve_puuid_via_riot_api(name, tag, region=region_code, api_key=key_to_use)
            if success and acc_data:
                puuid = acc_data.get("puuid", "")
            else:
                # Still allow user to continue
                pass

        # If no PUUID from API, fallback to local identifier
        if not puuid:
            import hashlib
            puuid = hashlib.sha256(f"{name}#{tag}".encode()).hexdigest()[:36]

        # Enable/disable autostart
        enable_auto = self.autostart_var.get()
        set_autostart(enable_auto)

        # Save profile
        profile = save_profile(
            game_name=name,
            tag_line=tag,
            puuid=puuid,
            region=region_code,
            autostart=enable_auto
        )

        # Callback on UI thread
        self.after(0, lambda: self.on_success(profile))
