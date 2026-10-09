import os
import sys
import json
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

def is_pid_alive(pid: int) -> bool:
    """Verifies if given PID is currently active on the system."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

def is_riot_client_running() -> bool:
    """
    Checks if Riot Client is actively running.
    Inspects lockfile, verifies that the process PID is alive, and cleans stale files if dead.
    """
    lock_path = get_riot_client_lockfile_path()
    if not os.path.isfile(lock_path):
        return False
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        parts = content.split(":")
        if len(parts) >= 5:
            pid = int(parts[1])
            if is_pid_alive(pid):
                return True
            else:
                # Stale lockfile from previous dead session - remove to prevent false detection
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
                return False
    except Exception:
        pass
    return False

def launch_riot_client_process(exe_path: str) -> bool:
    """
    Launches RiotClientServices.exe in the user's interactive Windows session.
    Cleans up any dead lockfile first, and uses CIM/WMI or os.startfile for detached execution.
    """
    lock_path = get_riot_client_lockfile_path()
    if os.path.isfile(lock_path):
        try:
            os.remove(lock_path)
        except Exception:
            pass

    exe_dir = os.path.dirname(exe_path)

    # Method 1: Launch via WMI/CIM in interactive desktop session
    if sys.platform == "win32":
        try:
            cmd = [
                "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                f"$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = '\"{exe_path}\"'; CurrentDirectory = '{exe_dir}' }}; exit $res.ReturnValue"
            ]
            creationflags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            ret = subprocess.call(cmd, creationflags=creationflags)
            if ret == 0:
                return True
        except Exception:
            pass

        # Method 2: Fallback to os.startfile
        try:
            os.startfile(exe_path)
            return True
        except Exception:
            pass

    # Method 3: Standard subprocess fallback
    try:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen([exe_path], cwd=exe_dir, creationflags=flags)
        return True
    except Exception:
        pass

    return False

def ensure_riot_client_running(
    timeout_seconds: int = 20,
    status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Ensures Riot Client is active. If not running, launches it in the system tray and waits for lockfile.
    """
    if is_riot_client_running():
        return True, "Riot Client уже запущен"

    exe_path = find_riot_client_path()
    if not exe_path:
        return False, "Riot Client не найден на компьютере"

    if status_callback:
        status_callback("Запуск Riot Client...")

    success = launch_riot_client_process(exe_path)
    if not success:
        return False, "Не удалось запустить процесс Riot Client"

    # Wait for lockfile to be generated by the running client
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if is_riot_client_running():
            # Allow webserver port a brief moment to finish binding
            time.sleep(1.5)
            return True, "Riot Client успешно запущен"
        time.sleep(0.5)

    return False, "Таймаут ожидания запуска Riot Client"

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
    If auto_launch is True and Riot Client is closed, automatically starts it.
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
