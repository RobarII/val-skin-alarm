import sys
import os
import subprocess
import webbrowser
import httpx
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Callable
from packaging import version

from config import APP_VERSION, GITHUB_REPO, BASE_DIR

UPDATE_BAT_SCRIPT = """@echo off
chcp 65001 > nul
timeout /t 1 /nobreak > nul
if exist "%~dp0ValSkinAlarm.exe.new" (
    move /y "%~dp0ValSkinAlarm.exe.new" "%~dp0ValSkinAlarm.exe"
)
start "" "%~dp0ValSkinAlarm.exe"
del "%~f0"
"""

def check_for_updates() -> Optional[Dict[str, Any]]:
    """
    Checks GitHub Releases for a newer version than current APP_VERSION.
    Returns release info dictionary if an update is available, else None.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "ValSkinAlarm-Updater"})
            if resp.status_code != 200:
                return None
            data = resp.json()

        tag = data.get("tag_name", "").lstrip("v").strip()
        if not tag:
            return None

        # Compare versions
        current_v = version.parse(APP_VERSION)
        latest_v = version.parse(tag)

        if latest_v > current_v:
            # Look for ValSkinAlarm.exe asset
            download_url = None
            for asset in data.get("assets", []):
                if asset.get("name") == "ValSkinAlarm.exe":
                    download_url = asset.get("browser_download_url")
                    break

            return {
                "version": tag,
                "tag": data.get("tag_name"),
                "name": data.get("name") or f"Версия {tag}",
                "notes": data.get("body") or "",
                "html_url": data.get("html_url"),
                "download_url": download_url
            }

    except Exception as e:
        print(f"Update check failed: {e}")

    return None

def download_and_install_update(
    download_url: Optional[str],
    html_url: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[bool, str]:
    """
    Downloads new ValSkinAlarm.exe and restarts application using update.bat.
    If not frozen, opens the release page in the browser.
    """
    is_frozen = getattr(sys, "frozen", False)

    if not is_frozen:
        # Running from Python source -> open browser
        target_url = html_url or f"https://github.com/{GITHUB_REPO}/releases/latest"
        webbrowser.open(target_url)
        return True, "Открыта страница релиза в браузере (запуск из исходного кода)."

    if not download_url:
        target_url = html_url or f"https://github.com/{GITHUB_REPO}/releases/latest"
        webbrowser.open(target_url)
        return False, "Ссылка на скачивание EXE не найдена. Открыт браузер."

    target_new_exe = BASE_DIR / "ValSkinAlarm.exe.new"
    update_bat_path = BASE_DIR / "update.bat"

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            with client.stream("GET", download_url) as response:
                response.raise_for_status()
                total_bytes = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(target_new_exe, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_bytes > 0:
                                percent = downloaded / total_bytes
                                progress_callback(percent, f"Скачивание: {int(percent * 100)}%")

        # Write update.bat
        with open(update_bat_path, "w", encoding="utf-8") as f:
            f.write(UPDATE_BAT_SCRIPT)

        if progress_callback:
            progress_callback(1.0, "Перезапуск...")

        # Spawn update.bat detached
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd.exe", "/c", str(update_bat_path)],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True
        )

        # Terminate current app to allow replacement
        os._exit(0)

    except Exception as e:
        if target_new_exe.exists():
            try:
                target_new_exe.unlink()
            except Exception:
                pass
        return False, f"Ошибка при обновлении: {e}"
