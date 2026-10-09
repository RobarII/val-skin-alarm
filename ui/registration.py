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
            text="🎯 VALORANT SKIN ALARM",
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
        self.region_menu.pack(fill="x", pady=(0, 15))

        # Autostart switch
        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.autostart_switch = ctk.CTkSwitch(
            self.form_frame,
            text="Запускать как демон при старте Windows",
            variable=self.autostart_var,
            font=ctk.CTkFont(size=12)
        )
        self.autostart_switch.pack(anchor="w", pady=(0, 15))

        # Status / Feedback label
        reload_env()
        has_key = bool(RIOT_API_KEY)
        key_status = "🔑 Riot API ключ найден в .env" if has_key else "ℹ️ API ключ в .env не указан (будет локальный режим)"
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

        if not name or not tag:
            self.status_label.configure(
                text="⚠️ Пожалуйста, введите ваш Ник и Тег",
                text_color="#FD4556"
            )
            return

        self.submit_btn.configure(state="disabled", text="Проверка...")
        self.status_label.configure(text="Подключение...", text_color=("gray40", "gray60"))

        threading.Thread(target=self._process_registration, args=(name, tag), daemon=True).start()

    def _process_registration(self, name: str, tag: str):
        reg_str = self.region_var.get()
        region_code = "eu"
        if "(na)" in reg_str:
            region_code = "na"
        elif "(ap)" in reg_str:
            region_code = "ap"
        elif "(kr)" in reg_str:
            region_code = "kr"

        reload_env()
        puuid = ""

        # Try official Riot API if key is available
        if RIOT_API_KEY:
            success, msg, acc_data = resolve_puuid_via_riot_api(name, tag, region=region_code)
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
