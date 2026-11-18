from pathlib import Path
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "gold_monitor.db"
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

for directory in (DATA_DIR, REPORTS_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def validate_settings() -> list[str]:
    errors = []
    try:
        ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        errors.append(f"APP_TIMEZONE 不是有效时区：{TIMEZONE}")

    placeholder_keys = {"your-key", "your_api_key", "你的fred_api_key"}
    if FRED_API_KEY.lower() in placeholder_keys:
        errors.append("FRED_API_KEY 仍是示例值，请填写真实密钥或留空")
    return errors


def ensure_valid_settings() -> None:
    errors = validate_settings()
    if errors:
        raise RuntimeError("；".join(errors))
