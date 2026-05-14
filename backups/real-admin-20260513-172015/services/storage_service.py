from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def load_json(path: str | Path, default: Any):
    ensure_data_dir()
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = DATA_DIR / file_path
    if not file_path.exists():
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            raw = file.read().strip()
            if not raw:
                return default
            return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: str | Path, data: Any) -> None:
    ensure_data_dir()
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = DATA_DIR / file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=True)
