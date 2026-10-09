import os
import sys
import json
import time
import base64
import threading
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Callable

import requests
import urllib3
urllib3.disable_warnings()

from storage import load_wishlist
from valorant_api import load_or_fetch_catalog, get_skin_by_uuid

# Cache valorant version string in memory to avoid repeated network calls
_CACHED_VERSION: Optional[str] = None

def get_shard_for_region(region: str) -> str:
    r = region.lower()
    if r in ["latam", "br"]:
        return "na"
    return r

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
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            # 0x1000 = PROCESS_QUERY_LIMITED_INFORMATION
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

def read_lockfile_data() -> Optional[Dict[str, Any]]:
    """
    Reads active lockfile information.
    Verifies that the process PID is alive, removing stale lockfiles if dead.
    """
    lock_path = get_riot_client_lockfile_path()
    if not os.path.isfile(lock_path):
        return None
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        parts = content.split(":")
        if len(parts) >= 5:
            pid = int(parts[1])
            if is_pid_alive(pid):
                return {
                    "name": parts[0],
                    "pid": pid,
                    "port": int(parts[2]),
                    "password": parts[3],
                    "protocol": parts[4]
                }
            else:
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
    except Exception:
        pass
    return None

def is_riot_client_running() -> bool:
    """Checks if Riot Client is actively running."""
    return read_lockfile_data() is not None

def start_auto_minimize_watcher(duration_seconds: float = 8.0) -> None:
    """
    Lightweight background worker that watches for Riot Client top-level windows
    and minimizes them so they sit quietly in the tray without interrupting the user.
    """
    def worker():
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            start_time = time.time()
            minimized_set = set()
            while time.time() - start_time < duration_seconds:
                def enum_proc(hwnd, lParam):
                    if user32.IsWindowVisible(hwnd):
                        buff = ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(hwnd, buff, 256)
                        if buff.value == "Riot Client":
                            if hwnd not in minimized_set:
                                minimized_set.add(hwnd)
                                # 6 = SW_MINIMIZE
                                user32.ShowWindow(hwnd, 6)
                    return True

                cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(enum_proc)
                user32.EnumWindows(cb, 0)
                time.sleep(0.15)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()

def minimize_riot_client_windows() -> None:
    """Finds any visible Riot Client windows and minimizes them to the system tray."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        def enum_proc(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                buff = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buff, 256)
                if buff.value == "Riot Client":
                    user32.ShowWindow(hwnd, 6)
            return True
        cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(enum_proc)
        user32.EnumWindows(cb, 0)
    except Exception:
        pass

def launch_riot_client_process(exe_path: str) -> bool:
    """
    Launches RiotClientServices.exe in minimized / tray mode in the user's desktop session.
    Cleans up any dead lockfile first, and starts a watcher to ensure it minimizes cleanly.
    """
    lock_path = get_riot_client_lockfile_path()
    if os.path.isfile(lock_path):
        try:
            os.remove(lock_path)
        except Exception:
            pass

    exe_dir = os.path.dirname(exe_path)
    start_auto_minimize_watcher(duration_seconds=8.0)

    # Method 1: ShellExecuteW with SW_SHOWMINNOACTIVE (7) for instant, quiet startup
    if sys.platform == "win32":
        try:
            import ctypes
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", exe_path, None, exe_dir, 7)
            if ret > 32:
                return True
        except Exception:
            pass

        # Method 2: Launch via WMI/CIM in interactive desktop session
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

        # Method 3: Fallback to os.startfile
        try:
            os.startfile(exe_path)
            return True
        except Exception:
            pass

    # Method 4: Standard subprocess fallback
    try:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen([exe_path], cwd=exe_dir, creationflags=flags)
        return True
    except Exception:
        pass

    return False

def ensure_riot_client_running(
    timeout_seconds: int = 15,
    status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Ensures Riot Client is active. If not running, launches it and waits for lockfile.
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

    # Rapidly wait for lockfile to be generated by the running client
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if is_riot_client_running():
            return True, "Riot Client успешно запущен"
        time.sleep(0.2)

    return False, "Таймаут ожидания запуска Riot Client"

def get_current_client_version() -> str:
    """Returns cached VALORANT client version string."""
    global _CACHED_VERSION
    if _CACHED_VERSION:
        return _CACHED_VERSION
    try:
        r = requests.get("https://valorant-api.com/v1/version", timeout=2.0)
        if r.status_code == 200:
            vd = r.json().get("data", {})
            _CACHED_VERSION = f"{vd['branch']}-shipping-{vd['buildVersion']}-{vd['version'].split('.')[3]}"
            return _CACHED_VERSION
    except Exception:
        pass
    return "release-10.02-shipping-2-3329986"

def get_authenticated_session(
    region: str = "eu",
    auto_launch: bool = True,
    status_callback: Optional[Callable[[str], None]] = None,
    timeout_seconds: float = 16.0
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Fast and resilient session authentication directly via local Riot Client and Riot auth services.
    Uses direct RSO token polling + cloud entitlements exchange, which avoids local SSL proxy freezes.
    Warm execution completes in <0.3s; cold start completes in ~3-4s.
    """
    lock_data = read_lockfile_data()
    if not lock_data:
        if auto_launch:
            launched, msg = ensure_riot_client_running(
                timeout_seconds=15,
                status_callback=status_callback
            )
            if not launched:
                return False, f"Не удалось запустить Riot Client: {msg}", None
            lock_data = read_lockfile_data()
        else:
            return False, "Riot Client не запущен.", None

    if not lock_data:
        return False, "Не удалось прочитать lockfile Riot Client.", None

    if status_callback:
        status_callback("Авторизация сессии...")

    access_token = None
    puuid = None
    player_name = "Player"
    player_tag = "0000"
    token = None
    last_port = None
    last_headers = None

    start_auth = time.time()
    while time.time() - start_auth < timeout_seconds:
        fresh_lock = read_lockfile_data()
        if fresh_lock:
            last_port = fresh_lock["port"]
            auth_b64 = base64.b64encode(f"riot:{fresh_lock['password']}".encode()).decode()
            last_headers = {"Authorization": f"Basic {auth_b64}"}

            # 1. Fast path: try local entitlements endpoint (instant if ready)
            if not token:
                try:
                    r_loc = requests.get(
                        f"https://127.0.0.1:{last_port}/entitlements/v1/token",
                        headers=last_headers,
                        verify=False,
                        timeout=0.6
                    )
                    if r_loc.status_code == 200:
                        loc_j = r_loc.json()
                        if "token" in loc_j:
                            token = loc_j["token"]
                        if not access_token and "accessToken" in loc_j:
                            access_token = loc_j["accessToken"]
                        if not puuid and "subject" in loc_j:
                            puuid = loc_j["subject"]
                except Exception:
                    pass

            # 2. Resilient path: direct RSO access token (fast and bypasses proxy)
            if not access_token:
                try:
                    r_at = requests.get(
                        f"https://127.0.0.1:{last_port}/rso-auth/v1/authorization/access-token",
                        headers=last_headers,
                        verify=False,
                        timeout=0.6
                    )
                    if r_at.status_code == 200:
                        at_json = r_at.json()
                        if "token" in at_json:
                            access_token = at_json["token"]
                except Exception:
                    pass

            # 3. Direct RSO puuid
            if not puuid:
                try:
                    r_subj = requests.get(
                        f"https://127.0.0.1:{last_port}/rso-auth/v1/authorization",
                        headers=last_headers,
                        verify=False,
                        timeout=0.6
                    )
                    if r_subj.status_code == 200:
                        subj_json = r_subj.json()
                        if "subject" in subj_json:
                            puuid = subj_json["subject"]
                except Exception:
                    pass

            # 4. Direct cloud exchange if local entitlements didn't provide JWT
            if access_token and not token:
                try:
                    r_ent = requests.post(
                        "https://entitlements.auth.riotgames.com/api/token/v1",
                        headers={"Authorization": f"Bearer {access_token}"},
                        json={},
                        timeout=3.0
                    )
                    if r_ent.status_code == 200:
                        ent_json = r_ent.json()
                        if "entitlements_token" in ent_json:
                            token = ent_json["entitlements_token"]
                except Exception:
                    pass

            # 5. Retrieve Player Alias
            if player_name == "Player" or player_tag == "0000":
                try:
                    r_alias = requests.get(
                        f"https://127.0.0.1:{last_port}/player-account/aliases/v1/active",
                        headers=last_headers,
                        verify=False,
                        timeout=0.6
                    )
                    if r_alias.status_code == 200:
                        alias_json = r_alias.json()
                        player_name = alias_json.get("game_name", player_name)
                        player_tag = alias_json.get("tag_line", player_tag)
                except Exception:
                    pass

                if player_name == "Player" or player_tag == "0000":
                    try:
                        r_chat = requests.get(
                            f"https://127.0.0.1:{last_port}/chat/v1/session",
                            headers=last_headers,
                            verify=False,
                            timeout=0.6
                        )
                        if r_chat.status_code == 200:
                            chat_json = r_chat.json()
                            player_name = chat_json.get("game_name", player_name)
                            player_tag = chat_json.get("game_tag", player_tag)
                            if not puuid:
                                puuid = chat_json.get("puuid", puuid)
                    except Exception:
                        pass

            if access_token and puuid and token:
                minimize_riot_client_windows()
                break

        time.sleep(0.2)

    # Final fallback checks if anything was missed during polling
    if not access_token or not puuid or not token:
        if last_port and last_headers:
            try:
                r_fallback = requests.get(
                    f"https://127.0.0.1:{last_port}/entitlements/v1/token",
                    headers=last_headers,
                    verify=False,
                    timeout=2.0
                )
                if r_fallback.status_code == 200:
                    fb_data = r_fallback.json()
                    if not access_token and "accessToken" in fb_data:
                        access_token = fb_data["accessToken"]
                    if not puuid and "subject" in fb_data:
                        puuid = fb_data["subject"]
                    if not token and "token" in fb_data:
                        token = fb_data["token"]
            except Exception:
                pass

    if not access_token or not puuid:
        return False, "Не удалось получить токен авторизации (Riot Client еще не вошел в аккаунт).", None

    if not token:
        try:
            r_ent_final = requests.post(
                "https://entitlements.auth.riotgames.com/api/token/v1",
                headers={"Authorization": f"Bearer {access_token}"},
                json={},
                timeout=5.0
            )
            if r_ent_final.status_code == 200:
                token = r_ent_final.json().get("entitlements_token")
        except Exception:
            pass

    if not token:
        return False, "Не удалось получить токен entitlements от Riot Games.", None

    client_platform = "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
    client_version = get_current_client_version()

    pvp_headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Riot-Entitlements-JWT": token,
        "X-Riot-ClientPlatform": client_platform,
        "X-Riot-ClientVersion": client_version
    }

    session_info = {
        "puuid": puuid,
        "player_name": player_name,
        "player_tag": player_tag,
        "headers": pvp_headers,
        "region": region,
        "shard": get_shard_for_region(region)
    }

    return True, "Авторизация успешна", session_info

def detect_current_player(
    region: str = "eu",
    auto_launch: bool = True,
    timeout_seconds: float = 12.0
) -> Optional[Dict[str, str]]:
    """
    Instantly detects player game name, tag line, and PUUID from active Riot Client session.
    Queries local Riot Client chat/alias endpoints directly in milliseconds without waiting for store tokens.
    """
    lock_data = read_lockfile_data()
    if not lock_data:
        if auto_launch:
            launched, _ = ensure_riot_client_running(timeout_seconds=12)
            if not launched:
                return None
            lock_data = read_lockfile_data()
        else:
            return None

    if not lock_data:
        return None

    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        fresh_lock = read_lockfile_data()
        if fresh_lock:
            port = fresh_lock["port"]
            auth_b64 = base64.b64encode(f"riot:{fresh_lock['password']}".encode()).decode()
            headers = {"Authorization": f"Basic {auth_b64}"}

            game_name = ""
            tag_line = ""
            puuid = ""

            # Method 1: /player-account/aliases/v1/active (fastest and earliest ready)
            try:
                resp = requests.get(
                    f"https://127.0.0.1:{port}/player-account/aliases/v1/active",
                    headers=headers,
                    verify=False,
                    timeout=0.8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    game_name = data.get("game_name", "")
                    tag_line = data.get("tag_line", "")
            except Exception:
                pass

            # Method 2: /rso-auth/v1/authorization (for PUUID)
            try:
                resp = requests.get(
                    f"https://127.0.0.1:{port}/rso-auth/v1/authorization",
                    headers=headers,
                    verify=False,
                    timeout=0.8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    puuid = data.get("subject", "")
            except Exception:
                pass

            # Method 3: /chat/v1/session (fallback for name, tag, and puuid)
            if not game_name or not tag_line or not puuid:
                try:
                    resp = requests.get(
                        f"https://127.0.0.1:{port}/chat/v1/session",
                        headers=headers,
                        verify=False,
                        timeout=0.8
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if not game_name:
                            game_name = data.get("game_name", "")
                        if not tag_line:
                            tag_line = data.get("game_tag", "")
                        if not puuid:
                            puuid = data.get("puuid", "")
                except Exception:
                    pass

            if game_name and tag_line:
                minimize_riot_client_windows()
                return {
                    "game_name": game_name,
                    "tag_line": tag_line,
                    "puuid": puuid,
                    "region": region
                }

        time.sleep(0.2)

    return None

def fetch_live_storefront(
    region: str = "eu",
    auto_launch: bool = True,
    status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Fetches the player's personal daily storefront via local Riot Client session.
    Ultra-fast execution: warm fetch takes ~0.5s, cold auto-launch takes ~5-7s.
    """
    success, msg, session = get_authenticated_session(
        region=region,
        auto_launch=auto_launch,
        status_callback=status_callback
    )
    if not success or not session:
        return False, msg, None

    if status_callback:
        status_callback("Получение ассортимента магазина...")

    shard = session["shard"]
    puuid = session["puuid"]
    headers = session["headers"]

    raw_store = None
    # Primary endpoint: POST /store/v3/storefront/{puuid}
    try:
        resp = requests.post(
            f"https://pd.{shard}.a.pvp.net/store/v3/storefront/{puuid}",
            headers=headers,
            json={},
            timeout=5.0
        )
        if resp.status_code == 200:
            raw_store = resp.json()
    except Exception:
        pass

    # Fallback: POST /storefront/v2/players/{puuid}
    if not raw_store:
        try:
            resp = requests.post(
                f"https://pd.{shard}.a.pvp.net/storefront/v2/players/{puuid}",
                headers=headers,
                json={},
                timeout=5.0
            )
            if resp.status_code == 200:
                raw_store = resp.json()
        except Exception:
            pass

    if not raw_store:
        return False, "Не удалось получить данные магазина (сервер Riot не ответил).", None

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
        "puuid": puuid,
        "player_name": session["player_name"],
        "player_tag": session["player_tag"]
    }

    return True, "Магазин успешно обновлен через Riot Client", data
