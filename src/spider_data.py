"""Spider dataset paths and prompt formatting (parallel to HumanEval for coding)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPIDER_ROOT = PROJECT_ROOT / "data" / "spider" / "spider"
SPIDER_DATABASE_DIR = SPIDER_ROOT / "database"
SPIDER_DEV_JSON = SPIDER_ROOT / "dev.json"

# Community mirror (see taoyds/spider issue #103) when official Yale link is down.
SPIDER_DOWNLOAD_URL = (
    "https://drive.google.com/uc?id=1TqleXec_OykOYFREKKtschzY29dUcVAQ"
)
SPIDER_ZIP_PATH = PROJECT_ROOT / "data" / "spider" / "spider_data.zip"


def spider_installed() -> bool:
    return SPIDER_DEV_JSON.is_file() and SPIDER_DATABASE_DIR.is_dir()


def spider_db_path(db_id: str) -> Path:
    return SPIDER_DATABASE_DIR / db_id / f"{db_id}.sqlite"


def spider_schema_path(db_id: str) -> Path:
    return SPIDER_DATABASE_DIR / db_id / "schema.sql"


@lru_cache(maxsize=1)
def load_spider_dev() -> list[dict]:
    with SPIDER_DEV_JSON.open() as f:
        return json.load(f)


def format_schema(db_id: str) -> str:
    schema_file = spider_schema_path(db_id)
    if schema_file.is_file():
        return schema_file.read_text().strip()
    return f"(schema file missing for {db_id})"


def format_spider_prompt(question: str, db_id: str) -> str:
    schema = format_schema(db_id)
    return (
        "Database schema (SQLite):\n\n"
        f"{schema}\n\n"
        f"Question: {question.strip()}\n\n"
        "Write a single SQLite SELECT statement that answers the question."
    )


def spider_problem_id(split: str, index: int) -> str:
    return f"Spider/{split}_{index:04d}"
