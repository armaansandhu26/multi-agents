#!/usr/bin/env python3
"""Analyze bidding, confidence, pressure, and outcomes across experiment runs."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import AGENT_C_ID, AGENT_S_ID, domain_agent_for_task

AGENTS = [AGENT_C_ID, AGENT_S_ID]


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
    return sorted(dict.fromkeys(files))


def mean(values: list[float | int | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.mean(clean) if clean else None


def pct(numer: int, denom: int) -> str:
    return "n/a" if denom == 0 else f"{numer / denom:.0%}"


def confidence_bin(confidence: int | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence < 50:
        return "0-49"
    if confidence < 70:
        return "50-69"
    if confidence < 85:
        return "70-84"
    if confidence < 95:
        return "85-94"
    return "95-100"


def build_rows(run_file: Path) -> list[dict]:
    with run_file.open() as f:
        run = json.load(f)

    metadata = run.get("metadata", {})
    starters = metadata.get("problem_starters", [])

    rows: list[dict] = []
    scores = {AGENT_C_ID: 0.0, AGENT_S_ID: 0.0}
    prior_agent_state = {
        agent: {
            "prev_bid": None,
            "prev_confidence": None,
            "prev_selected": False,
            "prev_passed": None,
            "prev_lead_failed": False,
            "prev_team_failed": False,
        }
        for agent in AGENTS
    }

    total = len(starters)
    for problem_number, item in enumerate(starters, start=1):
        task = item["task"]
        expected = domain_agent_for_task(task)
        leader = item.get("starter_agent_id")
        passed = item.get("passed")
        reward = item.get("reward", {})
        pitch_bids = item.get("pitch_bids", {})
        phase = "early" if problem_number <= max(1, total // 2) else "late"

        for agent in AGENTS:
            partner = AGENT_S_ID if agent == AGENT_C_ID else AGENT_C_ID
            bid = pitch_bids.get(agent, {})
            selected = agent == leader
            aligned = agent == expected
            confidence = bid.get("confidence")
            row = {
                "run_file": run_file.name,
                "run_id": run.get("run_id"),
                "condition": run.get("condition"),
                "seed": metadata.get("seed"),
                "problem_number": problem_number,
                "phase": phase,
                "task": task,
                "problem_id": item.get("problem_id"),
                "agent": agent,
                "aligned_with_task": aligned,
                "bid": bid.get("bid", "UNKNOWN"),
                "wants_lead": bid.get("wants_lead"),
                "confidence": confidence,
                "confidence_bin": confidence_bin(confidence),
                "claim": bid.get("claim"),
                "selected": selected,
                "team_passed": passed,
                "leader_passed": passed if selected else None,
                "leader_failed": (passed is False) if selected else False,
                "score_before": scores[agent],
                "partner_score_before": scores[partner],
                "score_gap_before": scores[agent] - scores[partner],
                "behind_before": scores[agent] < scores[partner],
                **prior_agent_state[agent],
            }
            rows.append(row)

        if reward.get("scores_after"):
            scores = dict(reward["scores_after"])

        for agent in AGENTS:
            agent_bid = pitch_bids.get(agent, {})
            selected = agent == leader
            prior_agent_state[agent] = {
                "prev_bid": agent_bid.get("bid", "UNKNOWN"),
                "prev_confidence": agent_bid.get("confidence"),
                "prev_selected": selected,
                "prev_passed": passed if selected else None,
                "prev_lead_failed": (passed is False) if selected else False,
                "prev_team_failed": passed is False,
            }

    return rows


def summarize(rows: list[dict]) -> None:
    if not rows:
        print("No structured pitch rows found.")
        return

    run_count = len({r["run_file"] for r in rows})
    problem_count = len({(r["run_file"], r["problem_number"]) for r in rows})
    print(f"Behavior rows: {len(rows)} agent-bids from {problem_count} problems across {run_count} runs")

    print("\nBid distribution")
    for key, group in group_counts(rows, ["bid"]).items():
        print(f"  {key[0]}: {len(group)}")

    print("\nLead bids by task alignment")
    for aligned in (True, False):
        group = [r for r in rows if r["aligned_with_task"] is aligned]
        lead = sum(1 for r in group if r["bid"] == "LEAD")
        label = "aligned" if aligned else "less-aligned"
        print(f"  {label}: {lead}/{len(group)} LEAD ({pct(lead, len(group))})")

    print("\nSelected leader calibration")
    leaders = [r for r in rows if r["selected"]]
    for conf_bin, group in group_counts(leaders, ["confidence_bin"]).items():
        passed = sum(1 for r in group if r["leader_passed"] is True)
        avg_conf = mean([r["confidence"] for r in group])
        avg_conf_text = "n/a" if avg_conf is None else f"{avg_conf:.0f}%"
        print(
            f"  conf {conf_bin[0]:>7}: n={len(group)} pass={passed}/{len(group)} "
            f"({pct(passed, len(group))}), avg_conf={avg_conf_text}"
        )

    print("\nAll bids: confidence vs eventual team outcome")
    for conf_bin, group in group_counts(rows, ["confidence_bin"]).items():
        passed = sum(1 for r in group if r["team_passed"] is True)
        lead_bids = sum(1 for r in group if r["bid"] == "LEAD")
        print(
            f"  conf {conf_bin[0]:>7}: n={len(group)} team_pass={pct(passed, len(group))}, "
            f"LEAD={pct(lead_bids, len(group))}"
        )

    print("\nDoes failure lead to caution on the next problem?")
    after_own_fail = [r for r in rows if r["prev_lead_failed"]]
    after_team_fail = [r for r in rows if r["prev_team_failed"]]
    after_no_team_fail = [r for r in rows if r["prev_team_failed"] is False and r["problem_number"] > 1]
    print_transition("after own leader failure", after_own_fail)
    print_transition("after team failure", after_team_fail)
    print_transition("after no team failure", after_no_team_fail)

    print("\nScore pressure: are agents behind more likely to seek leadership?")
    for behind in (True, False):
        group = [r for r in rows if r["behind_before"] is behind]
        lead = sum(1 for r in group if r["bid"] == "LEAD")
        avg_conf = mean([r["confidence"] for r in group])
        label = "behind" if behind else "tied/ahead"
        avg_conf_text = "n/a" if avg_conf is None else f"{avg_conf:.0f}%"
        print(f"  {label}: {lead}/{len(group)} LEAD ({pct(lead, len(group))}), avg_conf={avg_conf_text}")

    print("\nEarly vs late")
    for phase, group in group_counts(rows, ["phase"]).items():
        lead = sum(1 for r in group if r["bid"] == "LEAD")
        defer = sum(1 for r in group if r["bid"] == "DEFER")
        avg_conf = mean([r["confidence"] for r in group])
        avg_conf_text = "n/a" if avg_conf is None else f"{avg_conf:.0f}%"
        print(
            f"  {phase[0]}: LEAD={lead}/{len(group)} ({pct(lead, len(group))}), "
            f"DEFER={defer}, avg_conf={avg_conf_text}"
        )

    print("\nPer-agent summary")
    for agent, group in group_counts(rows, ["agent"]).items():
        lead = sum(1 for r in group if r["bid"] == "LEAD")
        selected = sum(1 for r in group if r["selected"])
        leader_pass = sum(1 for r in group if r["leader_passed"] is True)
        leader_total = sum(1 for r in group if r["selected"])
        avg_conf = mean([r["confidence"] for r in group])
        avg_conf_text = "n/a" if avg_conf is None else f"{avg_conf:.0f}%"
        print(
            f"  {agent[0]}: LEAD={pct(lead, len(group))}, selected={selected}/{len(group)}, "
            f"leader_pass={leader_pass}/{leader_total}, avg_conf={avg_conf_text}"
        )

    print("\nProblem timeline")
    for (run_file, problem_number), group in group_counts(rows, ["run_file", "problem_number"]).items():
        first = group[0]
        bits = []
        for row in sorted(group, key=lambda r: r["agent"]):
            bits.append(
                f"{short_agent(row['agent'])}:{row['bid']}@{row['confidence']}%"
                f"{'*' if row['selected'] else ''}"
            )
        outcome = "PASS" if first["team_passed"] else "FAIL"
        print(
            f"  {run_file} #{problem_number} {first['task']} {first['problem_id']} "
            f"{outcome}: " + " | ".join(bits)
        )


def group_counts(rows: list[dict], keys: list[str]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return dict(sorted(groups.items(), key=lambda item: item[0]))


def print_transition(label: str, group: list[dict]) -> None:
    lead = sum(1 for r in group if r["bid"] == "LEAD")
    defer = sum(1 for r in group if r["bid"] == "DEFER")
    avg_conf = mean([r["confidence"] for r in group])
    avg_conf_text = "n/a" if avg_conf is None else f"{avg_conf:.0f}%"
    print(
        f"  {label}: n={len(group)}, LEAD={pct(lead, len(group))}, "
        f"DEFER={defer}, avg_conf={avg_conf_text}"
    )


def short_agent(agent: str) -> str:
    return "C" if agent == AGENT_C_ID else "S"


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote behavior rows to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze bidding/confidence behavior across runs")
    parser.add_argument("run_file", nargs="+", help="Path or glob, e.g. runs/run_C_*.json")
    parser.add_argument("--csv", type=Path, help="Optional CSV output path for per-agent bid rows")
    args = parser.parse_args()

    run_files = resolve_run_files(args.run_file)
    if not run_files:
        print("No run files found.", file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = []
    skipped: Counter[str] = Counter()
    for run_file in run_files:
        run_rows = build_rows(run_file)
        if run_rows:
            rows.extend(run_rows)
        else:
            skipped[run_file.name] += 1

    summarize(rows)
    if args.csv:
        write_csv(rows, args.csv)
    if skipped:
        print(f"\nSkipped {sum(skipped.values())} run(s) without structured pitch data.")


if __name__ == "__main__":
    main()
