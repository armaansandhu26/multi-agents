#!/usr/bin/env python3
"""Check whether domain-expert framing is visible in a saved run."""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import AGENT_C_ID, AGENT_S_ID, domain_agent_for_task

CODE_MARKERS = re.compile(
    r"\b(python|algorithm|software engineer|code|function|implementation)\b",
    re.I,
)
SQL_MARKERS = re.compile(
    r"\b(sql|database|schema|query|join|table|sqlite)\b",
    re.I,
)


def resolve_run_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        path = Path(pattern)
        if path.is_file():
            candidates = [path]
        else:
            parent = path.parent if path.parent != Path(".") else Path("runs")
            glob_pattern = path.name if path.name else "run_*.json"
            candidates = sorted(parent.glob(glob_pattern))
        files.extend(
            p for p in candidates if p.is_file() and not p.name.endswith("_analysis.json")
        )
    return files


def score_domain_language(text: str) -> tuple[int, int]:
    return len(CODE_MARKERS.findall(text)), len(SQL_MARKERS.findall(text))


def analyze_volunteers(metadata: dict) -> None:
    starters = metadata.get("problem_starters", [])
    if not starters:
        print("No volunteer metadata found (was this run with --starter-mode volunteer?)")
        return

    domain_match = 0
    on_domain_lead = 0
    off_domain_defer = 0
    on_domain_total = 0
    off_domain_total = 0
    total = 0

    print("\nVolunteer phase:")
    for item in starters:
        if "volunteer_wants_lead" not in item:
            continue
        task = item["task"]
        expected = domain_agent_for_task(task)
        other = AGENT_S_ID if expected == AGENT_C_ID else AGENT_C_ID
        wants = item["volunteer_wants_lead"]
        starter = item["starter_agent_id"]
        total += 1
        if starter == expected:
            domain_match += 1
        on_domain_total += 1
        off_domain_total += 1
        if wants.get(expected):
            on_domain_lead += 1
        if not wants.get(other):
            off_domain_defer += 1
        print(
            f"  {task} {item['problem_id']}: "
            f"C={'LEAD' if wants.get(AGENT_C_ID) else 'DEFER'} "
            f"S={'LEAD' if wants.get(AGENT_S_ID) else 'DEFER'} "
            f"-> starter={starter} ({item.get('selection_reason', '?')})"
        )

    if total:
        print(f"\nDomain-matched agent led {domain_match}/{total} problems.")
        print(
            f"On-domain agent bid LEAD {on_domain_lead}/{on_domain_total}; "
            f"off-domain agent bid DEFER {off_domain_defer}/{off_domain_total}."
        )


def analyze_turn_language(turns: list[dict]) -> None:
    by_agent = {
        AGENT_C_ID: {"code": 0, "sql": 0, "turns": 0},
        AGENT_S_ID: {"code": 0, "sql": 0, "turns": 0},
    }
    for turn in turns:
        if turn.get("kind", "agent") != "agent":
            continue
        agent = turn["agent_id"]
        code_hits, sql_hits = score_domain_language(turn.get("content", ""))
        by_agent[agent]["code"] += code_hits
        by_agent[agent]["sql"] += sql_hits
        by_agent[agent]["turns"] += 1

    print("\nDomain language in discussion turns:")
    for agent, stats in by_agent.items():
        label = "code_expert" if agent == AGENT_C_ID else "sql_expert"
        print(
            f"  {label}: coding markers={stats['code']}, sql markers={stats['sql']}, "
            f"turns={stats['turns']}"
        )


def analyze_anchor_takeover(metadata: dict) -> None:
    """
    Test whether one agent increasingly leads across domains as the session progresses.
    Anchor takeover: starter stops matching domain expert and converges on one agent.
    """
    starters = metadata.get("problem_starters", [])
    volunteer_items = [s for s in starters if "volunteer_wants_lead" in s]
    if len(volunteer_items) < 2:
        return

    print("\nAnchor takeover check (volunteer pattern over session):")
    c_leads = 0
    s_leads = 0
    domain_aligned = 0

    for i, item in enumerate(volunteer_items, start=1):
        task = item["task"]
        expected = domain_agent_for_task(task)
        starter = item["starter_agent_id"]
        wants = item["volunteer_wants_lead"]
        aligned = starter == expected
        if aligned:
            domain_aligned += 1
        if starter == AGENT_C_ID:
            c_leads += 1
        else:
            s_leads += 1
        takeover = "" if aligned else f" TAKEOVER (domain={expected})"
        print(
            f"  #{i} {task}: starter={starter}, "
            f"C={'LEAD' if wants.get(AGENT_C_ID) else 'DEFER'} "
            f"S={'LEAD' if wants.get(AGENT_S_ID) else 'DEFER'}{takeover}"
        )

    n = len(volunteer_items)
    half = n // 2
    first_half = volunteer_items[:half]
    second_half = volunteer_items[half:]

    def domain_rate(items: list[dict]) -> float:
        if not items:
            return 0.0
        hits = sum(
            1 for item in items if item["starter_agent_id"] == domain_agent_for_task(item["task"])
        )
        return hits / len(items)

    def single_agent_rate(items: list[dict], agent: str) -> float:
        if not items:
            return 0.0
        hits = sum(1 for item in items if item["starter_agent_id"] == agent)
        return hits / len(items)

    early_domain = domain_rate(first_half)
    late_domain = domain_rate(second_half)
    early_c = single_agent_rate(first_half, AGENT_C_ID)
    late_c = single_agent_rate(second_half, AGENT_C_ID)
    early_s = single_agent_rate(first_half, AGENT_S_ID)
    late_s = single_agent_rate(second_half, AGENT_S_ID)

    print(f"\n  Domain-expert led: early={early_domain:.0%} late={late_domain:.0%}")
    print(f"  code_expert led:   early={early_c:.0%} late={late_c:.0%}")
    print(f"  sql_expert led:    early={early_s:.0%} late={late_s:.0%}")

    if late_domain < early_domain and (late_c == 1.0 or late_s == 1.0):
        print("  → Possible anchor takeover: one agent leads all late problems.")
    elif late_domain >= early_domain:
        print("  → Domain expertise still selects leader; no takeover detected.")
    else:
        print("  → Mixed pattern; need more problems/replicates to confirm takeover.")


def analyze_pitch_rewards(metadata: dict) -> None:
    starters = metadata.get("problem_starters", [])
    scoreboard = metadata.get("scoreboard", {})
    history = scoreboard.get("history", [])

    if not history:
        return

    print("\nReward outcomes:")
    for record in history:
        print(
            f"  {record['problem_id']}: "
            f"{'PASS' if record['passed'] else 'FAIL'} "
            f"leader={record['leader']} "
            f"({record['leader_delta']:+.1f}/{record['follower_delta']:+.1f})"
        )
    if scoreboard.get("scores"):
        print(f"\nFinal cumulative scores: {scoreboard['scores']}")

    pitch_items = [s for s in starters if "pitches" in s]
    if pitch_items:
        print("\nPitch → moderator selections:")
        for i, item in enumerate(pitch_items, start=1):
            task = item["task"]
            expected = domain_agent_for_task(task)
            starter = item["starter_agent_id"]
            aligned = "✓" if starter == expected else "takeover?"
            print(
                f"  #{i} {task} {item['problem_id']}: moderator picked {starter} {aligned}"
            )


def analyze_one(run_file: Path) -> None:
    with run_file.open() as f:
        run = json.load(f)

    print(f"Manipulation check: {run_file.name}")
    print(f"Condition {run['condition']}, starter_mode={run.get('metadata', {}).get('starter_mode')}, tiebreak={run.get('metadata', {}).get('tiebreak', '?')}")
    schedule = run.get("metadata", {}).get("problem_schedule")
    if schedule:
        print("Problem order:", " -> ".join(item["task"] for item in schedule))

    analyze_volunteers(run.get("metadata", {}))
    analyze_anchor_takeover(run.get("metadata", {}))
    analyze_pitch_rewards(run.get("metadata", {}))
    analyze_turn_language(run.get("turns", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manipulation check for expert framing")
    parser.add_argument(
        "run_file",
        nargs="+",
        help="Path or glob, e.g. runs/run_C_*.json",
    )
    args = parser.parse_args()

    run_files = resolve_run_files(args.run_file)
    if not run_files:
        print("No run files found.", file=sys.stderr)
        sys.exit(1)

    for run_file in run_files:
        print("=" * 72)
        analyze_one(run_file)


if __name__ == "__main__":
    main()
