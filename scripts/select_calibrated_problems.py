#!/usr/bin/env python3
"""Select calibrated problems from baseline results for coding and SQL.

Reads runs/baseline_calibration.json, finds problems in the 40-70% solo pass
band, promotes them to tier=calibrated in each bank, and writes balanced
experiment batteries (coding_calibrated.json, sql_calibrated.json).

Use --balance so both domains get the same battery size (matched difficulty).

Usage:
    python scripts/select_calibrated_problems.py
    python scripts/select_calibrated_problems.py --task coding
    python scripts/select_calibrated_problems.py --balance --target-size 20
    python scripts/select_calibrated_problems.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASELINE_PATH = ROOT / "runs" / "baseline_calibration.json"

TASK_CONFIG = {
    "coding": {
        "bank": ROOT / "data" / "problems" / "coding.json",
        "calibrated": ROOT / "data" / "problems" / "coding_calibrated.json",
    },
    "sql": {
        "bank": ROOT / "data" / "problems" / "sql.json",
        "calibrated": ROOT / "data" / "problems" / "sql_calibrated.json",
    },
}


def load_calibration_rates(task: str) -> dict[str, float]:
    with BASELINE_PATH.open() as f:
        calibration = json.load(f)
    return {
        r["problem_id"]: r["pass_rate"]
        for r in calibration
        if r["task"] == task and "pass_rate" in r
    }


def pick_in_band(
    bank: list[dict],
    rates: dict[str, float],
    *,
    band_low: float,
    band_high: float,
    band_center: float,
    target_size: int | None,
) -> tuple[list[dict], list[tuple[str, float, str]]]:
    """Return selected problems and a log of every calibrated candidate."""
    rows: list[tuple[dict, float]] = []
    log: list[tuple[str, float, str]] = []

    for problem in bank:
        pid = problem["id"]
        rate = rates.get(pid)
        if rate is None:
            continue
        in_band = band_low <= rate <= band_high
        status = "CALIBRATED" if in_band else "too easy" if rate > band_high else "too hard"
        log.append((pid, rate, status))
        if in_band:
            rows.append((problem, rate))

    rows.sort(key=lambda item: abs(item[1] - band_center))
    if target_size is not None:
        rows = rows[:target_size]

    selected = []
    for problem, rate in rows:
        updated = dict(problem)
        updated["tier"] = "calibrated"
        updated["calibration_pass_rate"] = rate
        selected.append(updated)
    return selected, log


def update_bank_tiers(bank: list[dict], selected_ids: set[str], rates: dict[str, float]) -> None:
    for problem in bank:
        if problem["id"] in selected_ids:
            problem["tier"] = "calibrated"
            problem["calibration_pass_rate"] = rates[problem["id"]]
        elif problem.get("tier") == "calibrated":
            problem["tier"] = "candidate"
            problem.pop("calibration_pass_rate", None)


def parity_report(
    selected: dict[str, list[dict]],
    *,
    min_battery: int,
) -> None:
    print("\n" + "=" * 60)
    print("Calibration parity")
    for task, problems in selected.items():
        if not problems:
            print(f"\n[{task}] 0 calibrated problems")
            continue
        rates = [p["calibration_pass_rate"] for p in problems]
        print(f"\n[{task}] {len(problems)} problems in battery")
        print(f"  pass rate mean: {statistics.mean(rates):.0%}")
        print(f"  pass rate stdev: {statistics.pstdev(rates):.0%}")
        print(f"  pass rate range: {min(rates):.0%}-{max(rates):.0%}")

    counts = [len(selected[t]) for t in selected]
    if len(set(counts)) > 1:
        print("\nWarning: battery sizes differ across tasks.")
    elif counts and counts[0] < min_battery:
        print(
            f"\nWarning: fewer than {min_battery} problems per task. "
            "Widen the band, run more baseline attempts, or expand candidate banks."
        )

    if len(counts) == 2 and counts[0] > 0 and counts[1] > 0:
        coding_mean = statistics.mean(p["calibration_pass_rate"] for p in selected["coding"])
        sql_mean = statistics.mean(p["calibration_pass_rate"] for p in selected["sql"])
        gap = abs(coding_mean - sql_mean)
        if gap > 0.1:
            print(
                f"\nWarning: mean pass rates differ by {gap:.0%} "
                f"(coding {coding_mean:.0%}, sql {sql_mean:.0%}). "
                "Batteries may not be equally difficult."
            )
        else:
            print(f"\nMean pass rates within {gap:.0%} — batteries look matched.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["coding", "sql", "both"], default="both")
    parser.add_argument("--band-low", type=float, default=0.4)
    parser.add_argument("--band-high", type=float, default=0.7)
    parser.add_argument(
        "--band-center",
        type=float,
        default=0.55,
        help="When trimming to target size, prefer rates closest to this value",
    )
    parser.add_argument(
        "--target-size",
        type=int,
        default=None,
        help="Max problems per task in the experiment battery",
    )
    parser.add_argument(
        "--balance",
        action="store_true",
        help="Set target size to the smaller in-band count across selected tasks",
    )
    parser.add_argument("--min-battery", type=int, default=6, help="Warn if below this count")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not BASELINE_PATH.exists():
        print(f"No calibration file at {BASELINE_PATH}. Run:", file=sys.stderr)
        print("  python scripts/run_baseline.py --task coding --tier candidate --attempts 5", file=sys.stderr)
        print("  python scripts/run_baseline.py --task sql --tier candidate --attempts 5", file=sys.stderr)
        sys.exit(1)

    tasks = ["coding", "sql"] if args.task == "both" else [args.task]
    print(f"Target band: {args.band_low:.0%}-{args.band_high:.0%} solo pass\n")

    in_band_counts: dict[str, int] = {}
    banks: dict[str, list[dict]] = {}
    rates_by_task: dict[str, dict[str, float]] = {}

    for task in tasks:
        rates = load_calibration_rates(task)
        rates_by_task[task] = rates
        with TASK_CONFIG[task]["bank"].open() as f:
            banks[task] = json.load(f)

        in_band_counts[task] = sum(
            1
            for problem in banks[task]
            if (rate := rates.get(problem["id"])) is not None
            and args.band_low <= rate <= args.band_high
        )
        print(f"[{task}] {in_band_counts[task]} in-band / {len(rates)} calibrated candidates")

    target_size = args.target_size
    if args.balance and args.task == "both":
        counts = [in_band_counts[t] for t in tasks]
        if all(count > 0 for count in counts):
            target_size = min(counts)
            print(f"\nBalancing batteries to {target_size} problems per task")
        else:
            print(
                "\nCannot balance yet — at least one task has no in-band problems. "
                "Finish baseline on both candidate banks first."
            )

    selected: dict[str, list[dict]] = {}
    for task in tasks:
        selected[task], _ = pick_in_band(
            banks[task],
            rates_by_task[task],
            band_low=args.band_low,
            band_high=args.band_high,
            band_center=args.band_center,
            target_size=target_size,
        )
        print(f"\n[{task}] selection ({len(selected[task])} chosen):")
        for problem in selected[task]:
            rate = problem["calibration_pass_rate"]
            print(f"  {problem['id']:20} pass={rate:.0%}  -> CALIBRATED")
        skipped = in_band_counts[task] - len(selected[task])
        if skipped:
            print(f"  ... and {skipped} other in-band problem(s) not included (size cap)")

    parity_report(
        selected,
        min_battery=args.min_battery,
    )

    if args.dry_run:
        print("\nDry run — no files written.")
        return

    for task in tasks:
        selected_ids = {p["id"] for p in selected[task]}
        update_bank_tiers(banks[task], selected_ids, rates_by_task[task])

        with TASK_CONFIG[task]["bank"].open("w") as f:
            json.dump(banks[task], f, indent=2)
            f.write("\n")

        with TASK_CONFIG[task]["calibrated"].open("w") as f:
            json.dump(selected[task], f, indent=2)
            f.write("\n")

        print(f"\nUpdated tiers in {TASK_CONFIG[task]['bank']}")
        print(f"Wrote battery to {TASK_CONFIG[task]['calibrated']}")


if __name__ == "__main__":
    main()
