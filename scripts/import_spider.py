#!/usr/bin/env python3
"""Import the Spider dev set into data/problems/sql.json (HumanEval-style setup).

Downloads the official Spider SQLite bundle if missing, verifies every gold
query executes, and writes one problem entry per dev example.

Usage:
    python scripts/import_spider.py              # download (if needed) + import dev
    python scripts/import_spider.py --verify     # verify only, no write
    python scripts/import_spider.py --max 50     # import first 50 dev examples (smoke)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.execution_grading import configure_sqlite_connection
from src.spider_data import (
    SPIDER_DATABASE_DIR,
    SPIDER_DEV_JSON,
    SPIDER_DOWNLOAD_URL,
    SPIDER_ROOT,
    SPIDER_ZIP_PATH,
    format_spider_prompt,
    spider_db_path,
    spider_installed,
    spider_problem_id,
)

SQL_PATH = ROOT / "data" / "problems" / "sql.json"
LEGACY_SQL_PATH = ROOT / "data" / "problems" / "sql_legacy.json"
WRONG_SQL = "SELECT 'deliberately_wrong_sentinel'"


def ensure_spider_data() -> None:
    if spider_installed():
        return

    SPIDER_ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Spider dataset to {SPIDER_ZIP_PATH} ...")
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "gdown",
                SPIDER_DOWNLOAD_URL,
                "-O",
                str(SPIDER_ZIP_PATH),
            ],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "Spider download failed. Install gdown (`pip install gdown`) or manually "
            f"extract the dataset to {SPIDER_ROOT}\n"
            f"Mirror: {SPIDER_DOWNLOAD_URL}"
        ) from exc

    print("Extracting ...")
    with zipfile.ZipFile(SPIDER_ZIP_PATH) as zf:
        zf.extractall(SPIDER_ZIP_PATH.parent)

    if not spider_installed():
        raise SystemExit(f"Extraction finished but {SPIDER_DEV_JSON} not found.")


def rows_match(
    con: sqlite3.Connection, candidate_sql: str, gold_sql: str, *, order_matters: bool
) -> bool:
    gold_rows = con.execute(gold_sql.rstrip().rstrip(";")).fetchall()
    try:
        cand_rows = con.execute(candidate_sql.rstrip().rstrip(";")).fetchall()
    except sqlite3.Error:
        return False
    if cand_rows and gold_rows and len(cand_rows[0]) != len(gold_rows[0]):
        return False
    if order_matters:
        return cand_rows == gold_rows
    return sorted(map(repr, cand_rows)) == sorted(map(repr, gold_rows))


def verify_item(item: dict, index: int) -> list[str]:
    errors = []
    db_id = item["db_id"]
    gold = item["query"]
    db_path = spider_db_path(db_id)

    if not db_path.is_file():
        return [f"missing database file {db_path}"]

    con = sqlite3.connect(db_path)
    configure_sqlite_connection(con)
    try:
        con.execute(gold.rstrip().rstrip(";")).fetchall()
    except sqlite3.Error as exc:
        return [f"gold query error: {exc}"]

    if not rows_match(con, gold, gold, order_matters=False):
        errors.append("gold query self-check failed")

    if rows_match(con, WRONG_SQL, gold, order_matters=False):
        errors.append("wrong sentinel query passed (non-discriminating)")

    return errors


def build_problem(item: dict, index: int, *, split: str = "dev") -> dict:
    db_id = item["db_id"]
    db_path = spider_db_path(db_id)
    rel_db_path = db_path.relative_to(ROOT).as_posix()
    return {
        "id": spider_problem_id(split, index),
        "source": "Spider",
        "split": split,
        "spider_index": index,
        "db_id": db_id,
        "db_path": rel_db_path,
        "tier": "candidate",
        "order_matters": False,
        "question": item["question"],
        "prompt": format_spider_prompt(item["question"], db_id),
        "gold_query": item["query"],
    }


def import_dev(*, max_problems: int | None, verify_only: bool) -> int:
    ensure_spider_data()
    with SPIDER_DEV_JSON.open() as f:
        dev = json.load(f)

    if max_problems is not None:
        dev = dev[:max_problems]

    failures = 0
    bank: list[dict] = []
    print(f"Verifying {len(dev)} Spider dev examples ...")
    for index, item in enumerate(dev):
        errors = verify_item(item, index)
        if errors:
            failures += 1
            print(f"  FAIL {spider_problem_id('dev', index)} ({item['db_id']}): {'; '.join(errors)}")
            continue
        bank.append(build_problem(item, index))
        if (index + 1) % 100 == 0 or index == len(dev) - 1:
            print(f"  verified {index + 1}/{len(dev)}")

    if failures:
        print(f"\n{failures} example(s) failed verification")
        return 1

    if verify_only:
        print(f"\nVerification passed for {len(bank)} examples (no files written).")
        return 0

    if SQL_PATH.is_file() and not LEGACY_SQL_PATH.is_file():
        shutil.copy2(SQL_PATH, LEGACY_SQL_PATH)
        print(f"Backed up previous sql.json to {LEGACY_SQL_PATH.name}")

    with SQL_PATH.open("w") as f:
        json.dump(bank, f, indent=2)
        f.write("\n")

    print(f"\nWrote {len(bank)} Spider problems to {SQL_PATH}")
    print("Next (mirror coding workflow):")
    print("  python scripts/import_humaneval.py")
    print("  python scripts/run_baseline.py --task coding --tier candidate --attempts 5")
    print("  python scripts/run_baseline.py --task sql --tier candidate --attempts 5")
    print("  python scripts/select_calibrated_problems.py --balance")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Spider dev set into sql.json")
    parser.add_argument("--verify", action="store_true", help="Verify only; do not write")
    parser.add_argument("--max", type=int, default=None, help="Import first N dev examples")
    args = parser.parse_args()
    raise SystemExit(import_dev(max_problems=args.max, verify_only=args.verify))


if __name__ == "__main__":
    main()
