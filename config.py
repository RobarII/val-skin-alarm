import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Project Root Directory (handles both python script and compiled PyInstaller .exe)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# Data and Cache paths
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"
IMAGES_CACHE_DIR = CACHE_DIR / "images"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# File paths
PROFILE_FILE = DATA_DIR / "profile.json"
WISHLIST_FILE = DATA_DIR / "wishlist.json"
SHOP_CACHE_FILE = DATA_DIR / "shop_cache.json"
CATALOG_CACHE_FILE = CACHE_DIR / "catalog.json"

# App details
APP_NAME = "VALORANT Skin Alarm"
APP_SUBTITLE = "Будильник скинов Валорант"
APP_VERSION = "1.0.0"
GITHUB_REPO = "RobarII/val-skin-alarm"

# Daily store reset hour (local time cutoff, default 06:00)
STORE_RESET_HOUR = 6

DEFAULT_ENV_CONTENT = """# Riot Games Developer API Key
# Получить персональный ключ можно бесплатно: https://developer.riotgames.com/
RIOT_API_KEY=

# Регион аккаунта (europe, americas, asia, esports)
# Для России и стран СНГ обычно europe
RIOT_REGION=europe
"""

def ensure_env_exists():
    """Unpacks .env and .env.example files next to executable if missing."""
    env_file = BASE_DIR / ".env"
    example_file = BASE_DIR / ".env.example"

    if not env_file.exists():
        try:
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(DEFAULT_ENV_CONTENT)
        except Exception as e:
            print(f"Failed to create .env: {e}")

    if not example_file.exists():
        try:
            with open(example_file, "w", encoding="utf-8") as f:
                f.write(DEFAULT_ENV_CONTENT)
        except Exception:
            pass

# Ensure .env is unpacked on startup
ensure_env_exists()

# Load .env
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

# API & Settings
RIOT_API_KEY = os.getenv("RIOT_API_KEY", "").strip()
RIOT_REGION = os.getenv("RIOT_REGION", "europe").strip().lower()

def reload_env():
    """Reloads settings from .env file"""
    global RIOT_API_KEY, RIOT_REGION
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    RIOT_API_KEY = os.getenv("RIOT_API_KEY", "").strip()
    RIOT_REGION = os.getenv("RIOT_REGION", "europe").strip().lower()

def open_env_in_editor():
    """Opens .env file in default system editor (e.g. Notepad)."""
    ensure_env_exists()
    try:
        if sys.platform == "win32":
            os.startfile(str(ENV_FILE))
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(ENV_FILE)])
        return True
    except Exception as e:
        print(f"Failed to open .env file: {e}")
        return False

def save_api_key_to_env(api_key: str, region: str = "europe") -> bool:
    """Saves Riot API key and region to .env file and reloads config."""
    try:
        content = f"""# Riot Games Developer API Key
# Получить персональный ключ можно бесплатно: https://developer.riotgames.com/
RIOT_API_KEY={api_key.strip()}

# Регион аккаунта (europe, americas, asia, esports)
# Для России и стран СНГ обычно europe
RIOT_REGION={region.strip().lower()}
"""
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        reload_env()
        return True
    except Exception as e:
        print(f"Failed to save .env file: {e}")
        return False
