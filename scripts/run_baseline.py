#!/usr/bin/env python3
"""Single-agent difficulty calibration with execution grading (Step 1).

Samples N independent solo attempts per problem, grades each by execution,
and reports per-problem pass rates. Problems in the target band (default
40-70% solo pass rate) are the recommended set for the main battery: hard
enough that failures happen, easy enough that collaboration can help.

Usage:
    python scripts/run_baseline.py                  # full bank, 5 attempts each
    python scripts/run_baseline.py --task coding --tier candidate --attempts 5
    python scripts/run_baseline.py --task sql --tier candidate --sample 200
    python scripts/run_baseline.py --report-only    # re-summarize last results
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.client import generate_response, make_client
from src.config import Settings
from src.execution_grading import grade_solution
from src.experiment import load_problems

OUTPUT_PATH = Path("runs") / "baseline_calibration.json"

SOLO_INSTRUCTIONS = (
    "Solve the problem correctly on your own. Think briefly if needed, then end "
    "your reply with a single fenced code block (```python or ```sql) containing "
    "your complete final solution. The code block will be executed and graded."
)


def save_results(results: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(results, f, indent=2)


def calibrate_task(
    task: str,
    settings: Settings,
    attempts: int,
    results: list[dict],
    *,
    tier: str | None = None,
    sample: int | None = None,
    sample_seed: int = 42,
) -> None:
    client = make_client(settings)
    done_ids = {r["problem_id"] for r in results if r["task"] == task}
    problems = load_problems(task, tier=tier)
    remaining = [p for p in problems if p["id"] not in done_ids]

    if sample is not None and len(remaining) > sample:
        rng = random.Random(sample_seed)
        remaining = rng.sample(remaining, sample)
        print(
            f"[{task}] sampling {sample} of {len(problems) - len(done_ids)} "
            f"remaining candidates (seed={sample_seed})",
            flush=True,
        )

    for problem in remaining:
        if problem["id"] in done_ids:
            print(f"[{task}] {problem['id']}: skipped (already calibrated)", flush=True)
            continue

        passes = 0
        attempt_details = []
        for i in range(attempts):
            response = generate_response(
                client,
                settings,
                instructions=SOLO_INSTRUCTIONS,
                input_messages=[
                    {"type": "message", "role": "user", "content": problem["prompt"]},
                ],
            )
            grade = grade_solution(problem, task, response)
            passes += grade.passed
            attempt_details.append(
                {"attempt": i + 1, "passed": grade.passed, "detail": grade.detail}
            )

        pass_rate = passes / attempts
        results.append(
            {
                "task": task,
                "problem_id": problem["id"],
                "tier": problem.get("tier"),
                "attempts": attempts,
                "passes": passes,
                "pass_rate": pass_rate,
                "attempt_details": attempt_details,
            }
        )
        save_results(results)
        print(
            f"[{task}] {problem['id']}: {passes}/{attempts} ({pass_rate:.0%})",
            flush=True,
        )


def summarize(results: list[dict], band_low: float, band_high: float) -> None:
    import statistics

    print("\n" + "=" * 60)
    print(f"Calibration summary (target band: {band_low:.0%}-{band_high:.0%} solo pass)")
    in_band_counts: dict[str, int] = {}
    in_band_means: dict[str, float] = {}

    for task in ("coding", "sql"):
        task_results = [r for r in results if r["task"] == task]
        if not task_results:
            print(f"\n[{task}] no results yet")
            continue
        in_band = [r for r in task_results if band_low <= r["pass_rate"] <= band_high]
        too_easy = [r for r in task_results if r["pass_rate"] > band_high]
        too_hard = [r for r in task_results if r["pass_rate"] < band_low]
        in_band_counts[task] = len(in_band)
        if in_band:
            in_band_means[task] = statistics.mean(r["pass_rate"] for r in in_band)

        print(f"\n[{task}] {len(task_results)} calibrated")
        print(f"  in band   ({len(in_band)}): {[r['problem_id'] for r in in_band]}")
        print(f"  too easy  ({len(too_easy)}): {len(too_easy)} problems")
        print(f"  too hard  ({len(too_hard)}): {len(too_hard)} problems")
        if in_band:
            print(f"  in-band mean pass rate: {in_band_means[task]:.0%}")

    if len(in_band_counts) == 2:
        coding_n = in_band_counts.get("coding", 0)
        sql_n = in_band_counts.get("sql", 0)
        print("\nParity check:")
        if coding_n == 0 or sql_n == 0:
            print("  One or both tasks have no in-band problems yet.")
        elif coding_n != sql_n:
            print(
                f"  In-band counts differ (coding {coding_n}, sql {sql_n}). "
                "Run select_calibrated_problems.py --balance after both finish."
            )
        if "coding" in in_band_means and "sql" in in_band_means:
            gap = abs(in_band_means["coding"] - in_band_means["sql"])
            print(
                f"  Mean in-band pass rates: coding {in_band_means['coding']:.0%}, "
                f"sql {in_band_means['sql']:.0%} (gap {gap:.0%})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Solo-agent difficulty calibration")
    parser.add_argument("--task", choices=["coding", "sql", "both"], default="both")
    parser.add_argument("--attempts", type=int, default=5, help="Solo attempts per problem")
    parser.add_argument("--band-low", type=float, default=0.4)
    parser.add_argument("--band-high", type=float, default=0.7)
    parser.add_argument(
        "--tier",
        default=None,
        help="Only calibrate problems with this tier tag (e.g. candidate, easy)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Randomly sample N uncaliibrated problems (for pilot runs)",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=42,
        help="RNG seed for --sample (default: 42)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Re-summarize the saved calibration file without calling the API",
    )
    args = parser.parse_args()

    if args.report_only:
        with OUTPUT_PATH.open() as f:
            results = json.load(f)
        summarize(results, args.band_low, args.band_high)
        return

    settings = Settings.from_env()
    tasks = ["coding", "sql"] if args.task == "both" else [args.task]
    results: list[dict] = []
    if OUTPUT_PATH.exists():
        with OUTPUT_PATH.open() as f:
            results = json.load(f)

    for task in tasks:
        calibrate_task(
            task,
            settings,
            args.attempts,
            results,
            tier=args.tier,
            sample=args.sample,
            sample_seed=args.sample_seed,
        )

    print(f"\nSaved calibration to {OUTPUT_PATH}", flush=True)

    summarize(results, args.band_low, args.band_high)


if __name__ == "__main__":
    main()
