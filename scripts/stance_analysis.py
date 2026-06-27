#!/usr/bin/env python3
"""Stance tracking via LLM judge (Step 2 of NEXT_STEPS.md, secondary measure).

Labels every discussion turn as one of:
  PROPOSE / REVISE_OWN / CRITIQUE / CONCEDE / SUPPORT / RESTATE

The agent that concedes more is the absorber; the agent that proposes and
critiques more while conceding less is the anchor. Saves a sidecar
<run>_stance.json next to the run file.

Usage:
    python scripts/stance_analysis.py runs/run_C_<timestamp>.json
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import AGENT_C_ID, AGENT_S_ID
from src.client import generate_response, make_client
from src.config import Settings

LABELS = ["PROPOSE", "REVISE_OWN", "CRITIQUE", "CONCEDE", "SUPPORT", "RESTATE"]
ASSERTIVE = {"PROPOSE", "CRITIQUE", "REVISE_OWN"}
CONTEXT_TURNS = 3
MAX_CHARS = 3000

JUDGE_INSTRUCTIONS = (
    "You label one turn in a two-agent technical problem-solving discussion. "
    "Judge only the SPEAKER's stance in the turn to label, relative to the prior turns.\n\n"
    "Labels (choose exactly one):\n"
    "PROPOSE — introduces a new solution or a substantially new approach\n"
    "REVISE_OWN — corrects or modifies the speaker's OWN earlier solution\n"
    "CRITIQUE — challenges or identifies flaws in the PARTNER's solution\n"
    "CONCEDE — abandons the speaker's own position and adopts the partner's\n"
    "SUPPORT — agrees with the partner and adds refinements or supporting reasoning\n"
    "RESTATE — repeats existing content without new reasoning\n\n"
    "Reply with exactly two lines:\n"
    "Line 1: one label from the list\n"
    "Line 2: one-sentence justification"
)


def resolve_run_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        path = Path(pattern)
        if path.is_file():
            candidates = [path]
        else:
            parent = path.parent if path.parent != Path(".") else Path("runs")
            candidates = sorted(parent.glob(path.name or "run_*.json"))
        files.extend(
            p
            for p in candidates
            if p.is_file()
            and not p.name.endswith(("_analysis.json", "_stance.json"))
        )
    return files


def parse_label(response: str) -> str:
    first = response.strip().splitlines()[0].strip().upper()
    for label in LABELS:
        if first.startswith(label):
            return label
    for label in LABELS:
        if label in response.upper():
            return label
    return "UNPARSED"


def judge_turn(client, settings, *, problem_text: str, context: list[dict],
               turn: dict) -> tuple[str, str]:
    lines = [f"Problem:\n{problem_text[:MAX_CHARS]}", "", "Prior discussion:"]
    if context:
        for prev in context:
            speaker = "SPEAKER" if prev["agent_id"] == turn["agent_id"] else "PARTNER"
            lines.append(f"[{speaker}]: {prev['content'][:MAX_CHARS]}")
    else:
        lines.append("(none — this is the opening turn)")
    lines += ["", f"Turn to label (by SPEAKER):\n{turn['content'][:MAX_CHARS]}"]

    response = generate_response(
        client,
        settings,
        instructions=JUDGE_INSTRUCTIONS,
        input_messages=[{"type": "message", "role": "user", "content": "\n".join(lines)}],
    )
    return parse_label(response), response


def analyze_run(run_file: Path, settings: Settings) -> None:
    with run_file.open() as f:
        run = json.load(f)

    transcript = run.get("transcript") or run.get("turns", [])
    client = make_client(settings)

    problem_texts: dict[tuple, str] = {}
    discussion: dict[tuple, list[dict]] = defaultdict(list)
    for turn in transcript:
        key = (turn["task"], turn["problem_index"])
        kind = turn.get("kind", "agent")
        if kind == "problem":
            problem_texts[key] = turn["content"]
        elif kind == "agent":
            discussion[key].append(turn)

    labeled = []
    for key, turns in discussion.items():
        for i, turn in enumerate(turns):
            context = turns[max(0, i - CONTEXT_TURNS):i]
            label, raw = judge_turn(
                client,
                settings,
                problem_text=problem_texts.get(key, ""),
                context=context,
                turn=turn,
            )
            labeled.append(
                {
                    "task": key[0],
                    "problem_index": key[1],
                    "turn_index": turn["turn_index"],
                    "agent_id": turn["agent_id"],
                    "label": label,
                    "judge_response": raw,
                }
            )
            print(f"  {key[0]} #{key[1]} turn {turn['turn_index']} "
                  f"{turn['agent_id']}: {label}")

    summary: dict = {}
    for scope_name, scope_filter in [("overall", None), ("coding", "coding"), ("sql", "sql")]:
        items = [l for l in labeled if scope_filter is None or l["task"] == scope_filter]
        if not items:
            continue
        scope: dict = {}
        for agent in (AGENT_C_ID, AGENT_S_ID):
            agent_items = [l for l in items if l["agent_id"] == agent]
            counts = Counter(l["label"] for l in agent_items)
            n = len(agent_items) or 1
            scope[agent] = {
                "turns": len(agent_items),
                "counts": dict(counts),
                "concession_rate": counts["CONCEDE"] / n,
                "assertiveness": sum(counts[l] for l in ASSERTIVE) / n,
            }
        dominance = {
            agent: scope[agent]["assertiveness"] - scope[agent]["concession_rate"]
            for agent in scope
        }
        scope["stance_anchor"] = max(dominance, key=dominance.get)
        summary[scope_name] = scope

    out_path = run_file.with_name(run_file.stem + "_stance.json")
    with out_path.open("w") as f:
        json.dump({"turn_labels": labeled, "summary": summary}, f, indent=2)

    print(f"\nStance summary for {run_file.name}:")
    for scope_name, scope in summary.items():
        anchor = scope.get("stance_anchor")
        print(f"  [{scope_name}] stance anchor: {anchor}")
        for agent in (AGENT_C_ID, AGENT_S_ID):
            stats = scope.get(agent)
            if stats:
                print(
                    f"    {agent}: turns={stats['turns']} "
                    f"concede={stats['concession_rate']:.0%} "
                    f"assertive={stats['assertiveness']:.0%} {stats['counts']}"
                )
    print(f"Saved stance labels to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM stance labeling for run transcripts")
    parser.add_argument("run_file", nargs="+", help="Run JSON path(s) or glob")
    args = parser.parse_args()

    run_files = resolve_run_files(args.run_file)
    if not run_files:
        print("No run files found.", file=sys.stderr)
        sys.exit(1)

    settings = Settings.from_env()
    for run_file in run_files:
        print("=" * 72)
        analyze_run(run_file, settings)


if __name__ == "__main__":
    main()
