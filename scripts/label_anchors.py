#!/usr/bin/env python3
"""Human anchor labeling + metric validation (Step 2 of NEXT_STEPS.md).

A metric is only a metric if it agrees with human judgment. This tool:

1. Interactive labeling — walks you through each problem's discussion and asks
   who anchored it. Labels are stored in runs/human_labels.json.

       python scripts/label_anchors.py runs/run_C_<timestamp>.json

2. Agreement report — compares your labels against each automated measure
   (provenance, stance, legacy lexical) and reports per-metric agreement.

       python scripts/label_anchors.py runs/run_C_<timestamp>.json --agreement
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import AGENT_C_ID, AGENT_S_ID
from src.metrics import compute_influence
from src.provenance import compute_provenance

LABELS_PATH = Path("runs") / "human_labels.json"
PREVIEW_CHARS = 500

CHOICES = {
    "c": AGENT_C_ID,
    "s": AGENT_S_ID,
    "n": "neither",
}


def load_labels() -> dict:
    if LABELS_PATH.exists():
        with LABELS_PATH.open() as f:
            return json.load(f)
    return {}


def save_labels(labels: dict) -> None:
    LABELS_PATH.parent.mkdir(exist_ok=True)
    with LABELS_PATH.open("w") as f:
        json.dump(labels, f, indent=2)


def group_problems(run: dict) -> dict[tuple, dict]:
    transcript = run.get("transcript") or run.get("turns", [])
    problems: dict[tuple, dict] = {}
    for turn in transcript:
        key = (turn["task"], turn["problem_index"])
        entry = problems.setdefault(
            key, {"problem": None, "turns": [], "final": None}
        )
        kind = turn.get("kind", "agent")
        if kind == "problem":
            entry["problem"] = turn["content"]
        elif kind == "agent":
            entry["turns"].append(turn)
        elif kind == "final":
            entry["final"] = turn
    return problems


def label_interactively(run_file: Path, run: dict, *, full: bool) -> None:
    labels = load_labels()
    run_labels = labels.setdefault(run_file.name, {})
    problems = group_problems(run)

    print(
        "\nFor each problem, decide who ANCHORED it: whose ideas drove the "
        "discussion and survived into the final solution?\n"
        "Keys: [c] code_expert  [s] sql_expert  [n] neither/unclear  "
        "[enter] skip  [q] quit\n"
    )

    for (task, idx), entry in sorted(problems.items(), key=lambda kv: kv[1]["turns"][0]["turn_index"] if kv[1]["turns"] else 0):
        key = f"{task}:{idx}"
        existing = run_labels.get(key)

        print("=" * 72)
        print(f"{task} #{idx}" + (f"  (already labeled: {existing})" if existing else ""))
        if entry["problem"]:
            print(f"\nPROBLEM:\n{entry['problem'][:PREVIEW_CHARS]}\n")
        for turn in entry["turns"]:
            content = turn["content"] if full else turn["content"][:PREVIEW_CHARS]
            suffix = "" if full or len(turn["content"]) <= PREVIEW_CHARS else " [...]"
            print(f"--- [{turn['agent_id']}] ---\n{content}{suffix}\n")
        if entry["final"]:
            content = entry["final"]["content"]
            print(f"--- FINAL SOLUTION (by {entry['final']['agent_id']}) ---\n"
                  f"{content[:PREVIEW_CHARS]}\n")

        while True:
            answer = input(f"Anchor for {key}? [c/s/n/enter=skip/q] ").strip().lower()
            if answer == "q":
                save_labels(labels)
                print(f"Saved labels to {LABELS_PATH}")
                return
            if answer == "":
                break
            if answer in CHOICES:
                run_labels[key] = CHOICES[answer]
                save_labels(labels)
                break
            print("Invalid choice.")

    save_labels(labels)
    print(f"\nDone. Labels saved to {LABELS_PATH}")


def metric_predictions(run: dict) -> dict[str, dict[str, str]]:
    """Per-problem anchor prediction from each automated metric."""
    predictions: dict[str, dict[str, str]] = defaultdict(dict)

    provenance = compute_provenance(run)
    for item in provenance["per_problem"]:
        key = f"{item['task']}:{item['problem_index']}"
        predictions["provenance"][key] = item["provenance_winner"]

    problems = group_problems(run)
    agents = [AGENT_C_ID, AGENT_S_ID]
    for (task, idx), entry in problems.items():
        if len(entry["turns"]) < 2:
            continue
        result = compute_influence(entry["turns"], agents)
        scores = result.anchor_scores
        predictions["legacy_lexical"][f"{task}:{idx}"] = max(scores, key=scores.get)

    return predictions


def stance_predictions(run_file: Path) -> dict[str, str]:
    """Per-problem stance anchor from the _stance.json sidecar, if present."""
    stance_path = run_file.with_name(run_file.stem + "_stance.json")
    if not stance_path.exists():
        return {}
    with stance_path.open() as f:
        stance = json.load(f)

    assertive = {"PROPOSE", "CRITIQUE", "REVISE_OWN"}
    by_problem: dict[str, dict[str, Counter]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for item in stance.get("turn_labels", []):
        key = f"{item['task']}:{item['problem_index']}"
        by_problem[key][item["agent_id"]][item["label"]] += 1

    predictions = {}
    for key, agent_counts in by_problem.items():
        dominance = {}
        for agent, counts in agent_counts.items():
            n = sum(counts.values()) or 1
            dominance[agent] = (
                sum(counts[l] for l in assertive) - counts["CONCEDE"]
            ) / n
        if dominance:
            predictions[key] = max(dominance, key=dominance.get)
    return predictions


def report_agreement(run_file: Path, run: dict) -> None:
    labels = load_labels().get(run_file.name, {})
    decided = {k: v for k, v in labels.items() if v in (AGENT_C_ID, AGENT_S_ID)}
    if not decided:
        print(
            f"No human labels for {run_file.name}. "
            "Run without --agreement to label first."
        )
        return

    predictions = metric_predictions(run)
    stance = stance_predictions(run_file)
    if stance:
        predictions["stance"] = stance

    print(f"\nMetric agreement vs human labels ({run_file.name}, "
          f"n={len(decided)} labeled problems):")
    for metric, preds in predictions.items():
        overlap = [k for k in decided if k in preds]
        if not overlap:
            print(f"  {metric}: no overlapping predictions")
            continue
        hits = sum(1 for k in overlap if preds[k] == decided[k])
        detail = ", ".join(
            f"{k}:{'OK' if preds[k] == decided[k] else 'X'}" for k in sorted(overlap)
        )
        print(f"  {metric}: {hits}/{len(overlap)} ({hits / len(overlap):.0%})  [{detail}]")
    if "stance" not in predictions:
        print("  stance: no sidecar found — run scripts/stance_analysis.py first")


def main() -> None:
    parser = argparse.ArgumentParser(description="Human anchor labeling + metric validation")
    parser.add_argument("run_file", help="Run JSON path")
    parser.add_argument("--agreement", action="store_true",
                        help="Report metric agreement instead of labeling")
    parser.add_argument("--full", action="store_true",
                        help="Show full turn text instead of previews")
    args = parser.parse_args()

    run_file = Path(args.run_file)
    if not run_file.is_file():
        print(f"Not found: {run_file}", file=sys.stderr)
        sys.exit(1)
    with run_file.open() as f:
        run = json.load(f)

    if args.agreement:
        report_agreement(run_file, run)
    else:
        label_interactively(run_file, run, full=args.full)


if __name__ == "__main__":
    main()
