from pathlib import Path

WEEK_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = WEEK_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
INDEX_PATH = DATA_DIR / "opossum_index.json"
