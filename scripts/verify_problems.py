#!/usr/bin/env python3
"""Offline verification of the problem bank (no API calls).

Checks:
- Coding: the canonical HumanEval solution passes the canonical tests through
  our own grading harness (validates both the data and the harness).
- Coding: a deliberately wrong solution FAILS (the harness can detect failure).
- SQL: every gold query runs against its fixture and returns at least one row.
- SQL: order_matters problems actually have an ORDER BY in the gold query.
- SQL: a deliberately wrong query FAILS comparison.

Run after any change to data/problems/ or src/execution_grading.py:
    python scripts/verify_problems.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.execution_grading import (
    open_sql_database,
    run_python_tests,
    run_sql_query,
    _execute_select,
)
from src.experiment import load_problems

WRONG_PYTHON = "def {entry_point}(*args, **kwargs):\n    return None\n"
WRONG_SQL = "SELECT 'deliberately_wrong_sentinel'"


def verify_coding() -> int:
    failures = 0
    problems = load_problems("coding")
    print(f"Coding bank: {len(problems)} problems")

    for problem in problems:
        canonical = problem["stub"] + problem["canonical_solution"]
        passed, detail = run_python_tests(
            canonical,
            stub=problem["stub"],
            test=problem["test"],
            entry_point=problem["entry_point"],
        )
        if not passed:
            failures += 1
            print(f"  FAIL {problem['id']}: canonical solution rejected — {detail}")
            continue

        wrong_passed, _ = run_python_tests(
            WRONG_PYTHON.format(entry_point=problem["entry_point"]),
            stub=problem["stub"],
            test=problem["test"],
            entry_point=problem["entry_point"],
        )
        if wrong_passed:
            failures += 1
            print(f"  FAIL {problem['id']}: wrong solution passed (tests too weak)")
        else:
            print(f"  ok   {problem['id']}")
    return failures


def verify_sql() -> int:
    failures = 0
    problems = load_problems("sql")
    spider_count = sum(1 for p in problems if p.get("source") == "Spider")
    legacy_count = len(problems) - spider_count
    print(
        f"\nSQL bank: {len(problems)} problems "
        f"({spider_count} Spider, {legacy_count} legacy/fixtures)"
    )

    for problem in problems:
        pid = problem["id"]
        gold = problem["gold_query"]
        try:
            rows = _execute_select(open_sql_database(problem), gold)
        except Exception as exc:
            failures += 1
            print(f"  FAIL {pid}: gold query error — {exc}")
            continue

        if not rows and problem.get("source") != "Spider" and not gold.strip().upper().startswith("SELECT COUNT"):
            failures += 1
            print(f"  FAIL {pid}: gold query returned no rows (non-discriminating)")
            continue

        if problem.get("order_matters") and "ORDER BY" not in gold.upper():
            failures += 1
            print(f"  FAIL {pid}: order_matters=true but gold query has no ORDER BY")
            continue

        gold_passed, _ = run_sql_query(
            gold, problem=problem, gold_query=gold, order_matters=problem.get("order_matters", False)
        )
        wrong_passed, _ = run_sql_query(
            WRONG_SQL,
            problem=problem,
            gold_query=gold,
            order_matters=problem.get("order_matters", False),
        )
        if not gold_passed:
            failures += 1
            print(f"  FAIL {pid}: gold query does not match itself (comparator bug)")
        elif wrong_passed:
            failures += 1
            print(f"  FAIL {pid}: wrong query passed comparison")
        else:
            print(f"  ok   {pid}: {len(rows)} rows — {rows[:4]}")
    return failures


def main() -> None:
    failures = verify_coding() + verify_sql()
    if failures:
        print(f"\n{failures} problem(s) failed verification")
        sys.exit(1)
    print("\nAll problems verified.")


if __name__ == "__main__":
    main()
