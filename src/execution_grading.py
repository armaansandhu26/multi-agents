"""Execution-based grading (Step 1 of NEXT_STEPS.md).

Replaces the LLM grader:
- Coding: run the extracted solution against the canonical HumanEval test suite
  in a sandboxed subprocess with a timeout.
- SQL: run the team's final query against a SQLite database (Spider `.sqlite`
  files or legacy in-memory fixtures), and compare its result set to the gold
  query's result set.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PYTHON_TIMEOUT_SECONDS = 15
SQL_MAX_VM_STEPS = 5_000_000

CODE_BLOCK_RE = re.compile(r"```([a-zA-Z]*)[ \t]*\n(.*?)```", re.DOTALL)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_PATH = PROJECT_ROOT / "data" / "problems" / "sql_fixtures.json"
_fixtures_cache: dict | None = None


@dataclass
class GradeResult:
    passed: bool
    detail: str
    extracted_solution: str | None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "detail": self.detail,
            "extracted_solution": self.extracted_solution,
        }


# ---------------------------------------------------------------------------
# Solution extraction
# ---------------------------------------------------------------------------

def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Return (language, body) for each fenced code block, in order."""
    return [(lang.lower(), body) for lang, body in CODE_BLOCK_RE.findall(text)]


def extract_python_solution(text: str, entry_point: str) -> str | None:
    """Prefer the last fenced block defining the entry point; fall back gracefully."""
    blocks = extract_code_blocks(text)
    def_pattern = re.compile(rf"def\s+{re.escape(entry_point)}\s*\(")

    for _, body in reversed(blocks):
        if def_pattern.search(body):
            return body.strip()
    for lang, body in reversed(blocks):
        if lang in ("python", "py", "") and "def " in body:
            return body.strip()
    # Last resort: unfenced code — take everything from the entry point's def.
    match = def_pattern.search(text)
    if match:
        return text[match.start():].strip()
    return None


def extract_sql_solution(text: str) -> str | None:
    """Prefer the last fenced sql block; fall back to the last SELECT/WITH statement."""
    blocks = extract_code_blocks(text)

    def last_select(body: str) -> str | None:
        statements = [s.strip() for s in body.split(";") if s.strip()]
        selects = [
            s for s in statements if s.upper().startswith(("SELECT", "WITH"))
        ]
        return selects[-1] if selects else None

    for lang, body in reversed(blocks):
        if lang in ("sql", "sqlite"):
            candidate = last_select(body)
            if candidate:
                return candidate
    for _, body in reversed(blocks):
        candidate = last_select(body)
        if candidate:
            return candidate
    # Unfenced fallback: last SELECT/WITH up to a semicolon or end of text.
    matches = list(re.finditer(r"(?is)\b(SELECT|WITH)\b", text))
    if matches:
        tail = text[matches[-1].start():]
        return tail.split(";")[0].strip()
    return None


# ---------------------------------------------------------------------------
# Python grading
# ---------------------------------------------------------------------------

def run_python_tests(
    solution: str,
    *,
    stub: str,
    test: str,
    entry_point: str,
    timeout: int = PYTHON_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Execute stub + solution + canonical tests in an isolated subprocess.

    The stub is executed first so helper functions defined in the problem prompt
    (e.g. HumanEval/32's `poly`) are available; the solution then redefines the
    entry point.
    """
    harness = "\n\n".join(
        [
            stub,
            "# --- candidate solution ---",
            solution,
            "# --- canonical tests ---",
            test,
            f"check({entry_point})",
            "print('ALL_TESTS_PASSED')",
        ]
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(harness)
        harness_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, "-I", harness_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"
    finally:
        Path(harness_path).unlink(missing_ok=True)

    if proc.returncode == 0 and "ALL_TESTS_PASSED" in proc.stdout:
        return True, "All canonical tests passed"
    error_tail = (proc.stderr or proc.stdout).strip()[-500:]
    return False, f"Tests failed: {error_tail}"


# ---------------------------------------------------------------------------
# SQL grading
# ---------------------------------------------------------------------------

def load_fixtures() -> dict:
    global _fixtures_cache
    if _fixtures_cache is None:
        with _FIXTURES_PATH.open() as f:
            _fixtures_cache = json.load(f)
    return _fixtures_cache


def build_fixture_db(fixture: dict) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    for ddl in fixture["schema"]:
        con.execute(ddl)
    for insert in fixture["inserts"]:
        con.execute(insert)
    con.commit()
    return con


def _normalize_row(row: tuple) -> tuple:
    return tuple(round(v, 6) if isinstance(v, float) else v for v in row)


def _execute_select(con: sqlite3.Connection, query: str, *, guard_runaway: bool = False) -> list[tuple]:
    if guard_runaway:
        con.set_progress_handler(lambda: 1, SQL_MAX_VM_STEPS)
    try:
        rows = con.execute(query.rstrip().rstrip(";")).fetchall()
    finally:
        if guard_runaway:
            con.set_progress_handler(None, 0)
    return [_normalize_row(r) for r in rows]


def configure_sqlite_connection(con: sqlite3.Connection) -> None:
    con.text_factory = lambda b: b.decode("utf-8", errors="replace")


def open_sql_database(problem: dict) -> sqlite3.Connection:
    """Open the SQLite DB for a SQL problem (Spider file or legacy fixture)."""
    if problem.get("source") == "Spider" or problem.get("db_path"):
        db_path = Path(problem.get("db_path", ""))
        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path
        if not db_path.is_file():
            from src.spider_data import spider_db_path

            db_path = spider_db_path(problem["db_id"])
        con = sqlite3.connect(db_path)
        configure_sqlite_connection(con)
        return con

    fixture = load_fixtures()[problem["db_id"]]
    con = build_fixture_db(fixture)
    configure_sqlite_connection(con)
    return con


def _use_runaway_guard(problem: dict) -> bool:
    return problem.get("source") != "Spider" and "db_path" not in problem


def run_sql_query(
    candidate_sql: str,
    *,
    problem: dict,
    gold_query: str,
    order_matters: bool = False,
) -> tuple[bool, str]:
    gold_rows = _execute_select(
        open_sql_database(problem), gold_query, guard_runaway=_use_runaway_guard(problem)
    )

    try:
        candidate_rows = _execute_select(
            open_sql_database(problem),
            candidate_sql,
            guard_runaway=_use_runaway_guard(problem),
        )
    except sqlite3.Error as exc:
        return False, f"SQL error: {exc}"

    if candidate_rows and gold_rows and len(candidate_rows[0]) != len(gold_rows[0]):
        return False, (
            f"Wrong number of columns: expected {len(gold_rows[0])}, "
            f"got {len(candidate_rows[0])}"
        )

    if order_matters:
        match = candidate_rows == gold_rows
    else:
        match = sorted(map(repr, candidate_rows)) == sorted(map(repr, gold_rows))

    if match:
        return True, f"Result matches gold ({len(gold_rows)} rows)"
    return False, (
        f"Result mismatch: expected {len(gold_rows)} rows, got {len(candidate_rows)} rows; "
        f"expected sample {gold_rows[:3]}, got sample {candidate_rows[:3]}"
    )


def run_sql_against_fixture(
    candidate_sql: str,
    *,
    db_id: str,
    gold_query: str,
    order_matters: bool = False,
) -> tuple[bool, str]:
    """Legacy helper for fixture-only verification scripts."""
    return run_sql_query(
        candidate_sql,
        problem={"db_id": db_id},
        gold_query=gold_query,
        order_matters=order_matters,
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def grade_solution(problem: dict, task: str, solution_text: str) -> GradeResult:
    """Grade the team's final solution text for a problem via execution."""
    if task == "coding":
        solution = extract_python_solution(solution_text, problem["entry_point"])
        if solution is None:
            return GradeResult(False, "No Python solution found in final answer", None)
        passed, detail = run_python_tests(
            solution,
            stub=problem["stub"],
            test=problem["test"],
            entry_point=problem["entry_point"],
        )
        return GradeResult(passed, detail, solution)

    if task == "sql":
        solution = extract_sql_solution(solution_text)
        if solution is None:
            return GradeResult(False, "No SQL query found in final answer", None)
        passed, detail = run_sql_query(
            solution,
            problem=problem,
            gold_query=problem["gold_query"],
            order_matters=problem.get("order_matters", False),
        )
        return GradeResult(passed, detail, solution)

    return GradeResult(False, f"Unknown task type: {task}", None)
