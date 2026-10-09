import threading
import customtkinter as ctk
from typing import Callable, Optional, Dict, Any

from storage import save_profile
from autostart import set_autostart, is_autostart_enabled
from riot_client import detect_current_player, ensure_riot_client_running, is_riot_client_running

class RegistrationFrame(ctk.CTkFrame):
    def __init__(self, master, on_success: Callable[[Dict[str, Any]], None], **kwargs):
        super().__init__(master, **kwargs)
        self.on_success = on_success

        self.pack(fill="both", expand=True, padx=20, pady=20)
        self._build_ui()
        self.after(200, self._try_auto_detect_player)

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
        self.name_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Ваш ник в игре", height=38, corner_radius=8)
        self.name_entry.pack(fill="x", pady=(0, 10))

        # TagLine Entry
        ctk.CTkLabel(self.form_frame, text="Тег (без #):", anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", pady=(5, 2))
        self.tag_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Например: RU1 или 0000", height=38, corner_radius=8)
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
        self.region_menu.pack(fill="x", pady=(0, 12))

        # Auto-detect button
        self.detect_btn = ctk.CTkButton(
            self.form_frame,
            text="Определить автоматически из Riot Client",
            height=32,
            corner_radius=6,
            fg_color=("gray85", "#27272a"),
            hover_color=("gray75", "#3f3f46"),
            text_color=("black", "white"),
            font=ctk.CTkFont(size=12),
            command=self._on_detect_clicked
        )
        self.detect_btn.pack(fill="x", pady=(0, 12))

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
        self.status_label = ctk.CTkLabel(
            self.form_frame,
            text="Введите ник или используйте автоопределение",
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

        self.detected_puuid = ""

    def _try_auto_detect_player(self):
        def worker():
            if is_riot_client_running():
                data = detect_current_player(auto_launch=False, timeout_seconds=3.0)
                if data and data.get("game_name"):
                    self.after(0, lambda: self._apply_detected_data(data))
        threading.Thread(target=worker, daemon=True).start()

    def _on_detect_clicked(self):
        self.detect_btn.configure(state="disabled", text="Поиск аккаунта в Riot Client...")
        self.status_label.configure(text="Подключение к Riot Client...", text_color=("gray40", "gray60"))

        def worker():
            data = detect_current_player(auto_launch=True, timeout_seconds=15.0)
            def update_ui():
                self.detect_btn.configure(state="normal", text="Определить автоматически из Riot Client")
                if data and data.get("game_name"):
                    self._apply_detected_data(data)
                else:
                    self.status_label.configure(text="Riot Client не запущен или в нем не выполнен вход", text_color="#ef4444")
            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_detected_data(self, data: Dict[str, str]):
        name = data.get("game_name", "")
        tag = data.get("tag_line", "")
        self.detected_puuid = data.get("puuid", "")

        if name:
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, name)
        if tag:
            self.tag_entry.delete(0, "end")
            self.tag_entry.insert(0, tag)

        self.status_label.configure(
            text=f"Аккаунт обнаружен: {name}#{tag}",
            text_color="#16a34a"
        )

    def _on_submit(self):
        name = self.name_entry.get().strip()
        tag = self.tag_entry.get().strip().lstrip("#")

        if not name or not tag:
            self.status_label.configure(
                text="Пожалуйста, введите ваш Ник и Тег",
                text_color="#FD4556"
            )
            return

        reg_str = self.region_var.get()
        region_code = "eu"
        if "(na)" in reg_str:
            region_code = "na"
        elif "(ap)" in reg_str:
            region_code = "ap"
        elif "(kr)" in reg_str:
            region_code = "kr"

        puuid = self.detected_puuid
        if not puuid:
            try:
                detected = detect_current_player(region=region_code, auto_launch=False, timeout_seconds=2.0)
                if detected and detected.get("puuid") and detected.get("game_name", "").lower() == name.lower():
                    puuid = detected.get("puuid")
            except Exception:
                pass
        if not puuid:
            import hashlib
            puuid = hashlib.sha256(f"{name}#{tag}".encode()).hexdigest()[:36]

        enable_auto = self.autostart_var.get()
        set_autostart(enable_auto)

        profile = save_profile(
            game_name=name,
            tag_line=tag,
            puuid=puuid,
            region=region_code,
            autostart=enable_auto
        )

        self.on_success(profile)
