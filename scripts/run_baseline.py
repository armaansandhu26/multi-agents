#!/usr/bin/env python3
"""
Single-agent baseline for difficulty calibration.

Run each problem alone and record whether the model produces a plausible solution.
Swap in stricter graders later (HumanEval execution harness, Spider exact-match).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.client import generate_response, make_client
from src.config import Settings
from src.experiment import load_problems


def run_baseline(task: str, settings: Settings) -> list[dict]:
    client = make_client(settings)
    results = []

    for problem in load_problems(task):
        prompt = problem["prompt"]
        response = generate_response(
            client,
            settings,
            instructions=(
                "Solve the problem correctly. Be concise but complete."
            ),
            input_messages=[
                {"type": "message", "role": "user", "content": prompt},
            ],
        )
        results.append(
            {
                "task": task,
                "problem_id": problem["id"],
                "response": response,
            }
        )
        print(f"[{task}] {problem['id']} — response length {len(response)} chars")

    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task",
        choices=["coding", "sql", "both"],
        default="both",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    tasks = ["coding", "sql"] if args.task == "both" else [args.task]
    all_results = []

    for task in tasks:
        all_results.extend(run_baseline(task, settings))

    out = Path("runs") / "baseline_single_agent.json"
    out.parent.mkdir(exist_ok=True)
    with out.open("w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved baseline to {out}")


if __name__ == "__main__":
    main()
