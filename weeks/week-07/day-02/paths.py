from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = DAY_DIR.parents[2]
DATA_DIR = DAY_DIR / "data"
SEEN_STATE_PATH = DATA_DIR / "seen_prs.json"
RAG_INDEX_PATH = DATA_DIR / "rag_index.json"
