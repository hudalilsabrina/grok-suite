import os
import sys
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Config file resolution
CONFIG_FILE = BASE_DIR / "config.toml"

_config = {}


def _load_config():
    global _config
    if _config:
        return _config
    if CONFIG_FILE.exists():
        try:
            if sys.version_info >= (3, 11):
                import tomllib
                with open(CONFIG_FILE, "rb") as f:
                    _config = tomllib.load(f)
            else:
                import tomli
                with open(CONFIG_FILE, "rb") as f:
                    _config = tomli.load(f)
        except Exception as e:
            print(f"[!] Warning: failed to parse config.toml: {e}")
            _config = {}
    return _config


def get_cfg(section, key, default=None):
    cfg = _load_config()
    return cfg.get(section, {}).get(key, default)


# ---- Temp-mail (self-hosted disposable inbox) ----
# Set via config.toml [api] tempmail_base, or env TEMPIK_BASE.
TEMPIK_BASE = os.getenv("TEMPIK_BASE", get_cfg("api", "tempmail_base", "http://localhost:8080/api"))

# ---- 9router ----
NINE_ROUTER_URL = os.getenv("NINEROUTER_URL", get_cfg("router", "url", "http://localhost:20127"))
NINE_ROUTER_PASS = os.getenv("NINEROUTER_PASS", get_cfg("router", "password", ""))

HEADLESS = os.getenv("GONKA_HEADLESS", str(get_cfg("general", "headless", True))).lower() in ("true", "1", "yes")

# Optional webhook notification (Slack/Discord/Telegram/any HTTP endpoint).
WEBHOOK_URL = os.getenv("GONKA_WEBHOOK_URL", get_cfg("notify", "webhook_url", ""))

# Structured JSON logging: set GONKA_JSON_LOG=1 or [logging] json = true
JSON_LOG = os.getenv("GONKA_JSON_LOG", str(get_cfg("logging", "json", False))).lower() in ("true", "1", "yes")

DATA_DIR = BASE_DIR / "data"
LOG_FILE = DATA_DIR / "app.log"
OUTPUT_TXT = BASE_DIR / "accounts.txt"
