from pathlib import Path

WEEK_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = WEEK_DIR / "data"
INDEX_PATH = DATA_DIR / "opossum_index.json"
DAY_DIR = Path(__file__).resolve().parent
HISTORY_PATH = DAY_DIR / "chat_history.json"
LOGS_DIR = DAY_DIR / "logs"
