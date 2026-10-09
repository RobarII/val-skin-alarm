import sys
import os
import winreg
from config import BASE_DIR

APP_REG_KEY_NAME = "ValorantSkinAlarm"

def _get_daemon_command() -> str:
    """Returns the command to launch in daemon mode silently."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --daemon'

    python_dir = os.path.dirname(sys.executable)
    pythonw_path = os.path.join(python_dir, "pythonw.exe")
    if not os.path.exists(pythonw_path):
        pythonw_path = sys.executable

    script_path = os.path.join(BASE_DIR, "main.py")
    return f'"{pythonw_path}" "{script_path}" --daemon'

def is_autostart_enabled() -> bool:
    """Checks if the application is set to start with Windows."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, APP_REG_KEY_NAME)
        winreg.CloseKey(key)
        return bool(value)
    except FileNotFoundError:
        return False
    except Exception:
        return False

def set_autostart(enable: bool) -> bool:
    """Enables or disables autostart in Windows Registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        if enable:
            cmd = _get_daemon_command()
            winreg.SetValueEx(key, APP_REG_KEY_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_REG_KEY_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Error updating autostart registry: {e}")
        return False
