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

# Load .env
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

# API & Settings
RIOT_API_KEY = os.getenv("RIOT_API_KEY", "").strip()
RIOT_REGION = os.getenv("RIOT_REGION", "europe").strip().lower()

# App details
APP_NAME = "VALORANT Skin Alarm"
APP_SUBTITLE = "Будильник скинов Валорант"
APP_VERSION = "1.0.0"

# Daily store reset hour (local time cutoff, default 06:00)
STORE_RESET_HOUR = 6

def reload_env():
    """Reloads settings from .env file"""
    global RIOT_API_KEY, RIOT_REGION
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    RIOT_API_KEY = os.getenv("RIOT_API_KEY", "").strip()
    RIOT_REGION = os.getenv("RIOT_REGION", "europe").strip().lower()
