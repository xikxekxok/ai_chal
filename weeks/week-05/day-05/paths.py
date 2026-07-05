from pathlib import Path

WEEK_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = WEEK_DIR / "data"
INDEX_PATH = DATA_DIR / "opossum_index.json"
HISTORY_PATH = Path(__file__).resolve().parent / "chat_history.json"
