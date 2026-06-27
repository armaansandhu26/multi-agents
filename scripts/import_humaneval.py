#!/usr/bin/env python3
"""Import the full HumanEval set into data/problems/coding.json.

Mirrors scripts/import_spider.py: every problem is tagged tier=candidate for
solo baseline calibration, then select_calibrated_problems.py picks the 40-70%
band for experiments.

Usage:
    python scripts/import_humaneval.py
    python scripts/import_humaneval.py --verify     # verify only, no write
    python scripts/import_humaneval.py --max 50     # first 50 problems (smoke)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eval.data import read_problems

from src.execution_grading import run_python_tests

CODING_PATH = ROOT / "data" / "problems" / "coding.json"
LEGACY_CODING_PATH = ROOT / "data" / "problems" / "coding_legacy.json"

WRONG_PYTHON = "def {entry_point}(*args, **kwargs):\n    return None\n"


def build_problem(task_id: str, item: dict) -> dict:
    stub = item["prompt"]
    return {
        "id": task_id,
        "source": "HumanEval",
        "tier": "candidate",
        "prompt": f"Write a Python function:\n\n{stub}",
        "stub": stub,
        "entry_point": item["entry_point"],
        "test": item["test"],
        "canonical_solution": item["canonical_solution"],
    }


def verify_problem(problem: dict) -> list[str]:
    errors: list[str] = []
    canonical = problem["stub"] + problem["canonical_solution"]
    passed, detail = run_python_tests(
        canonical,
        stub=problem["stub"],
        test=problem["test"],
        entry_point=problem["entry_point"],
    )
    if not passed:
        errors.append(f"canonical solution rejected — {detail}")
        return errors

    wrong_passed, _ = run_python_tests(
        WRONG_PYTHON.format(entry_point=problem["entry_point"]),
        stub=problem["stub"],
        test=problem["test"],
        entry_point=problem["entry_point"],
    )
    if wrong_passed:
        errors.append("wrong solution passed (tests too weak)")
    return errors


def import_humaneval(*, max_problems: int | None, verify_only: bool) -> int:
    raw = read_problems()
    task_ids = sorted(raw.keys(), key=lambda tid: int(tid.split("/")[1]))
    if max_problems is not None:
        task_ids = task_ids[:max_problems]

    failures = 0
    bank: list[dict] = []
    print(f"Verifying {len(task_ids)} HumanEval problems ...")
    for task_id in task_ids:
        problem = build_problem(task_id, raw[task_id])
        errors = verify_problem(problem)
        if errors:
            failures += 1
            print(f"  FAIL {task_id}: {'; '.join(errors)}")
            continue
        bank.append(problem)
        if len(bank) % 50 == 0 or task_id == task_ids[-1]:
            print(f"  verified {len(bank)}/{len(task_ids)}")

    if failures:
        print(f"\n{failures} problem(s) failed verification")
        return 1

    if verify_only:
        print(f"\nVerification passed for {len(bank)} problems (no files written).")
        return 0

    if CODING_PATH.is_file() and not LEGACY_CODING_PATH.is_file():
        shutil.copy2(CODING_PATH, LEGACY_CODING_PATH)
        print(f"Backed up previous coding.json to {LEGACY_CODING_PATH.name}")

    with CODING_PATH.open("w") as f:
        json.dump(bank, f, indent=2)
        f.write("\n")

    print(f"\nWrote {len(bank)} HumanEval problems to {CODING_PATH}")
    print("Next (same workflow as SQL):")
    print("  python scripts/run_baseline.py --task coding --tier candidate --attempts 5")
    print("  python scripts/run_baseline.py --task sql --tier candidate --attempts 5")
    print("  python scripts/select_calibrated_problems.py --balance")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Import HumanEval into coding.json")
    parser.add_argument("--verify", action="store_true", help="Verify only; do not write")
    parser.add_argument("--max", type=int, default=None, help="Import first N problems")
    args = parser.parse_args()
    raise SystemExit(import_humaneval(max_problems=args.max, verify_only=args.verify))


if __name__ == "__main__":
    main()
