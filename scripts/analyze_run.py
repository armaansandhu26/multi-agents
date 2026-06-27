#!/usr/bin/env python3
"""Analyze a saved experiment run for anchor-absorber dynamics."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import AGENT_C_ID, AGENT_S_ID
from src.metrics import classify_roles, compute_influence, detect_task_flip
from src.provenance import compute_provenance


def resolve_run_files(pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_file():
        candidates = [path]
    else:
        parent = path.parent if path.parent != Path(".") else Path("runs")
        glob_pattern = path.name if path.name else "run_*.json"
        candidates = sorted(parent.glob(glob_pattern))

    return [
        p
        for p in candidates
        if p.is_file() and not p.name.endswith("_analysis.json")
    ]


def analyze_one(run_file: Path) -> None:
    with run_file.open() as f:
        run = json.load(f)

    agents = [AGENT_C_ID, AGENT_S_ID]
    result = compute_influence(run["turns"], agents)
    roles = classify_roles(result.anchor_scores, result.absorber_scores)
    flip = detect_task_flip(result.by_task, agents)

    print(f"Run: {run['run_id']}  condition={run['condition']}  model={run['model']}")
    print(f"Task order: {' -> '.join(run['task_order'])}")
    if run.get("metadata", {}).get("problem_starters"):
        print("\nProblem starters:")
        for item in run["metadata"]["problem_starters"]:
            line = (
                f"  {item['task']} #{item['problem_index']} ({item['problem_id']}): "
                f"{item['starter_agent_id']}"
            )
            if "selection_reason" in item:
                line += f" [{item['selection_reason']}]"
            print(line)

    provenance = compute_provenance(run)
    if provenance["n_problems_scored"]:
        print("\nSolution provenance (PRIMARY anchoring measure):")
        print("  Whose first proposal does the final graded solution resemble?")
        for item in provenance["per_problem"]:
            leader_note = "" if item["winner_is_leader"] is None else (
                " (= leader)" if item["winner_is_leader"] else " (NOT leader)"
            )
            print(
                f"  {item['task']} #{item['problem_index']}: "
                f"winner={item['provenance_winner']}{leader_note} "
                f"margin={item['margin']:.3f}"
            )
        for task, stats in provenance["by_task"].items():
            print(
                f"  [{task}] anchor={stats['anchor']} wins={stats['wins']} "
                f"mean_combined={ {a: round(v, 3) for a, v in stats['mean_combined'].items()} }"
            )
        prov_flip = provenance["flip"]
        print(
            f"  Provenance flip across tasks: {prov_flip['flip_detected']} "
            f"({prov_flip['anchors']})"
        )
    else:
        print(
            "\nSolution provenance: no final-answer turns found "
            "(pre-Phase-3 run; provenance requires the new harness)."
        )

    print("\nLEGACY lexical influence I(source -> target), term-frequency cosine")
    print("(secondary measure: topical overlap, not validated influence):")
    for src in agents:
        for tgt in agents:
            if src == tgt:
                continue
            print(f"  I({src} -> {tgt}) = {result.influence[src][tgt]:.3f}")

    print("\nRole scores:")
    for agent in agents:
        print(
            f"  {agent}: anchor={result.anchor_scores[agent]:.3f}, "
            f"absorber={result.absorber_scores[agent]:.3f}, role={roles[agent]}"
        )

    print("\nBy task:")
    for task, matrix in result.by_task.items():
        print(f"  [{task}]")
        for src in agents:
            for tgt in agents:
                if src == tgt:
                    continue
                print(f"    I({src} -> {tgt}) = {matrix[src][tgt]:.3f}")

    print("\nTask-boundary flip check (H1):")
    print(f"  flip_detected: {flip['flip_detected']}")
    if "by_task" in flip:
        for task, stats in flip["by_task"].items():
            print(
                f"  {task}: I(C->S)={stats.get(f'I({AGENT_C_ID}->{AGENT_S_ID})', 0):.3f}, "
                f"I(S->C)={stats.get(f'I({AGENT_S_ID}->{AGENT_C_ID})', 0):.3f}, "
                f"dominant={stats['dominant']}"
            )

    out_path = run_file.with_name(run_file.stem + "_analysis.json")
    with out_path.open("w") as f:
        json.dump(
            {
                "provenance": provenance,
                "legacy_lexical": {
                    **result.to_dict(),
                    "roles": roles,
                    "task_flip": flip,
                },
            },
            f,
            indent=2,
        )
    print(f"\nSaved analysis to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute anchor-absorber influence metrics for a run JSON file"
    )
    parser.add_argument(
        "run_file",
        nargs="+",
        help="Path or glob, e.g. runs/run_A_20260601T171051Z.json or 'runs/run_A_*.json'",
    )
    args = parser.parse_args()

    run_files: list[Path] = []
    for pattern in args.run_file:
        run_files.extend(resolve_run_files(pattern))

    if not run_files:
        print("No run files found. Pass a path like runs/run_A_*.json", file=sys.stderr)
        sys.exit(1)

    for run_file in run_files:
        print("=" * 72)
        analyze_one(run_file)


if __name__ == "__main__":
    main()
