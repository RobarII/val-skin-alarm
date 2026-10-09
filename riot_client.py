import os
import sys
import json
import random
import time
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Callable

from storage import load_wishlist
from valorant_api import load_or_fetch_catalog, get_skin_by_uuid

def find_riot_client_path() -> Optional[str]:
    """
    Dynamically locates RiotClientServices.exe on Windows without hardcoded paths.
    Searches ProgramData manifest, Windows Registry, local AppData, and available drives.
    """
    # 1. Check official ProgramData manifest
    prog_data = os.environ.get("ALLUSERSPROFILE") or os.environ.get("ProgramData") or r"C:\ProgramData"
    manifest = os.path.join(prog_data, "Riot Games", "RiotClientInstalls.json")
    if os.path.isfile(manifest):
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key in ["rc_default", "rc_live"]:
                    p = data.get(key)
                    if p and os.path.isfile(p):
                        return os.path.normpath(p)
                for p in data.get("associated_client", {}).values():
                    if p and os.path.isfile(p):
                        return os.path.normpath(p)
        except Exception:
            pass

    # 2. Check Windows Registry
    if sys.platform == "win32":
        import winreg
        registry_locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Riot Games\RiotClient", "Path"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Riot Games\RiotClient", "Path"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Riot Games\RiotClient", "Path"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Riot Client", "InstallLocation"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Riot Client", "InstallLocation"),
        ]
        for hive, subkey, val_name in registry_locations:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    val, _ = winreg.QueryValueEx(k, val_name)
                    if val:
                        p = os.path.normpath(val)
                        if os.path.isfile(p):
                            return p
                        candidate = os.path.join(p, "RiotClientServices.exe")
                        if os.path.isfile(candidate):
                            return os.path.normpath(candidate)
            except OSError:
                pass

    # 3. Check Local AppData
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        p = os.path.join(local_app_data, "Riot Games", "Riot Client", "RiotClientServices.exe")
        if os.path.isfile(p):
            return os.path.normpath(p)

    # 4. Dynamically scan all available drive letters
    if sys.platform == "win32":
        import string
        subpaths = [
            r"Riot Games\Riot Client\RiotClientServices.exe",
            r"games\Riot Games\Riot Client\RiotClientServices.exe",
            r"Games\Riot Games\Riot Client\RiotClientServices.exe",
            r"Program Files\Riot Games\Riot Client\RiotClientServices.exe",
            r"Program Files (x86)\Riot Games\Riot Client\RiotClientServices.exe",
        ]
        for letter in string.ascii_uppercase:
            drive_root = f"{letter}:\\"
            if os.path.exists(drive_root):
                for sub in subpaths:
                    candidate = os.path.join(drive_root, sub)
                    if os.path.isfile(candidate):
                        return os.path.normpath(candidate)

    return None

def get_riot_client_lockfile_path() -> str:
    """Returns absolute path to Riot Client lockfile."""
    return os.path.join(
        os.getenv("LOCALAPPDATA", ""),
        r"Riot Games\Riot Client\Config\lockfile"
    )

def is_riot_client_running() -> bool:
    """Checks if Riot Client lockfile exists and contains session data."""
    lock_path = get_riot_client_lockfile_path()
    if not os.path.isfile(lock_path):
        return False
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            # lockfile format: process_name:pid:port:password:protocol
            return len(content.split(":")) >= 5
    except Exception:
        return False

def ensure_riot_client_running(
    timeout_seconds: int = 20,
    status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Ensures Riot Client is running in the background/system tray.
    If not running, autonomously launches RiotClientServices.exe with --launch-background-mode
    and waits for the session lockfile to initialize.
    """
    if is_riot_client_running():
        return True, "Riot Client уже запущен"

    exe_path = find_riot_client_path()
    if not exe_path:
        return False, "Riot Client не найден на компьютере"

    if status_callback:
        status_callback("Запуск Riot Client в трее...")

    try:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [exe_path, "--launch-background-mode"],
            startupinfo=startupinfo,
            creationflags=creationflags
        )
    except Exception as e:
        return False, f"Ошибка запуска Riot Client: {e}"

    # Wait for lockfile to be created
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if is_riot_client_running():
            # Give internal server a brief moment to initialize port
            time.sleep(1.0)
            return True, "Riot Client успешно запущен в трее"
        time.sleep(0.5)

    return False, "Таймаут инициализации Riot Client"

def detect_current_player(region: str = "eu") -> Optional[Dict[str, str]]:
    """
    Attempts to read player game name, tag and PUUID from active Riot Client session.
    """
    if not is_riot_client_running():
        return None

    try:
        import valclient
        import urllib3
        urllib3.disable_warnings()

        client = valclient.Client(region=region)
        client.activate()
        return {
            "game_name": client.player_name,
            "tag_line": client.player_tag,
            "puuid": client.puuid,
            "region": region
        }
    except Exception:
        return None

def fetch_live_storefront(
    region: str = "eu",
    auto_launch: bool = True
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Fetches the player's personal daily storefront via local Riot Client session.
    If auto_launch is True and Riot Client is closed, automatically starts it in the tray.
    """
    if not is_riot_client_running():
        if auto_launch:
            launched, msg = ensure_riot_client_running(timeout_seconds=20)
            if not launched:
                return False, f"Не удалось запустить Riot Client: {msg}", None
        else:
            return False, "Riot Client не запущен.", None

    try:
        import valclient
        import requests
        import urllib3
        urllib3.disable_warnings()

        client = valclient.Client(region=region)
        client.activate()

        raw_store = None
        # Primary endpoint: POST /store/v3/storefront/{puuid}
        try:
            resp = requests.post(
                f"https://pd.{client.shard}.a.pvp.net/store/v3/storefront/{client.puuid}",
                headers=client.headers,
                json={},
                timeout=12
            )
            if resp.status_code == 200:
                raw_store = resp.json()
        except Exception:
            pass

        # Fallback 1: POST /storefront/v2/players/{puuid}
        if not raw_store:
            try:
                resp = requests.post(
                    f"https://pd.{client.shard}.a.pvp.net/storefront/v2/players/{client.puuid}",
                    headers=client.headers,
                    json={},
                    timeout=12
                )
                if resp.status_code == 200:
                    raw_store = resp.json()
            except Exception:
                pass

        # Fallback 2: valclient built-in
        if not raw_store:
            try:
                raw_store = client.store_fetch_storefront()
            except Exception:
                pass

        if not raw_store:
            return False, "Не удалось получить данные магазина (сервер Riot не ответил).", None

        # SkinsPanelLayout contains the 4 daily offers
        panel = raw_store.get("SkinsPanelLayout", {})
        offers = panel.get("SingleItemOffers", [])
        duration = panel.get("SingleItemOffersRemainingDurationInSeconds", 86400)

        # Convert offers into catalog skin UUIDs
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

        return True, "Магазин успешно обновлен через Riot Client", data

    except Exception as e:
        return False, f"Ошибка подключения к Riot Client: {e}", None

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

    # If wishlist has items and chance is enabled, include at least one wishlist skin to trigger alarm
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
    expires_at = now_ts + 86400

    return {
        "skins": selected_uuids,
        "expires_at": expires_at,
        "duration_seconds": 86400,
        "source": "demo"
    }
