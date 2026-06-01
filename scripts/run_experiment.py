#!/usr/bin/env python3
"""Run one full experiment condition (A, B, or C)."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import Settings
from src.experiment import build_problem_schedule, run_experiment, save_run, task_order_label


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-agent anchoring experiment")
    parser.add_argument(
        "--condition",
        choices=["A", "B", "C"],
        default="A",
        help="A=coding block then SQL; B=SQL block then coding; C=interleaved",
    )
    parser.add_argument(
        "--starter-mode",
        choices=["pitch", "volunteer", "random", "alternate", "code", "sql"],
        default="pitch",
        help="pitch=moderator selects leader from pitches + rewards (default)",
    )
    parser.add_argument(
        "--tiebreak",
        choices=["random", "domain", "continuity"],
        default="random",
        help="Only used when starter-mode=volunteer and both bid LEAD",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for volunteer/random starter modes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print protocol summary without calling the API",
    )
    args = parser.parse_args()

    if args.dry_run:
        schedule = build_problem_schedule(args.condition)
        order = task_order_label(args.condition, schedule)
        print(f"Dry run: condition {args.condition}")
        print(f"Problem order: {' -> '.join(order)}")
        print(f"Starter mode: {args.starter_mode}, seed={args.seed}")
        if args.starter_mode == "pitch":
            print("Per problem: pitch -> moderator -> 6 turns -> grade -> rewards")
        print("Expected discussion turns: 36")
        return

    settings = Settings.from_env()
    run = run_experiment(
        settings,
        condition=args.condition,
        starter_mode=args.starter_mode,
        tiebreak=args.tiebreak,
        seed=args.seed,
    )

    path = save_run(run)
    print(f"Saved run to {path}")
    print(f"Discussion turns logged: {len(run.turns)}")
    scores = run.metadata.get("scoreboard", {}).get("scores", {})
    print(f"Final scores: {scores}")
    print("Run analysis with:")
    print(f"  python scripts/analyze_run.py {path}")
    print(f"  python scripts/manipulation_check.py {path}")


if __name__ == "__main__":
    main()
