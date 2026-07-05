from __future__ import annotations

import json
import sys
from typing import Any

from paths import INDEX_PATH


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        print(
            "[error] индекс не найден — сначала day-01: "
            "python weeks/week-05/day-01/init_data.py → "
            "python weeks/week-05/day-01/main.py --index",
            file=sys.stderr,
        )
        print(f"[error] ожидается: {INDEX_PATH}", file=sys.stderr)
        raise SystemExit(1)
    with INDEX_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)
