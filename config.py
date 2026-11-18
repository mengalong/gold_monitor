from pathlib import Path
import os
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
