#!/usr/bin/env python3
"""Create an HTML/SVG dashboard for bidding and confidence behavior."""

from __future__ import annotations

import argparse
import html
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.behavior_analysis import (  # noqa: E402
    AGENT_C_ID,
    AGENT_S_ID,
    build_rows,
    group_counts,
    mean,
    pct,
    resolve_run_files,
    short_agent,
)


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def bool_text(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def problem_key(row: dict) -> tuple:
    return (row["run_file"], row["problem_number"])


def event_trajectory_svg(rows: list[dict]) -> str:
    groups = group_counts(rows, ["run_file", "problem_number"])
    if not groups:
        return "<p>No pitch rows to plot.</p>"

    group_items = list(groups.items())
    event_count = len(group_items) * 3
    width = max(920, 78 * event_count + 120)
    height = 430
    left = 58
    right = 24
    top = 36
    bottom = 112
    plot_w = width - left - right
    plot_h = height - top - bottom
    step = plot_w / max(1, event_count - 1)

    def x_for(event_index: int, agent: str) -> float:
        offset = -5 if agent == AGENT_C_ID else 5
        return left + event_index * step + offset

    def y_for(conf: int | None) -> float:
        conf = 0 if conf is None else max(0, min(100, int(conf)))
        return top + (100 - conf) / 100 * plot_h

    elems: list[str] = []
    point_elems: list[str] = []
    elems.append(f'<svg class="chart event-chart" viewBox="0 0 {width} {height}" role="img">')
    elems.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis"/>')
    elems.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" class="axis"/>'
    )
    for tick in (0, 25, 50, 75, 100):
        y = y_for(tick)
        elems.append(f'<line x1="{left - 5}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        elems.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="tick">{tick}%</text>')

    elems.append(f'<text x="{left}" y="20" class="axis-label">Event trajectory: bid → selection → outcome</text>')

    polylines = {AGENT_C_ID: [], AGENT_S_ID: []}
    for idx, ((run_file, problem_number), group) in enumerate(group_items):
        first = group[0]
        base_event = idx * 3
        x_bid = left + base_event * step
        x_sel = left + (base_event + 1) * step
        x_out = left + (base_event + 2) * step
        band_x = min(x_bid, x_sel, x_out) - step * 0.45
        band_w = step * 2.9
        pass_class = "pass-band" if first["team_passed"] else "fail-band"
        elems.append(
            f'<rect x="{band_x:.1f}" y="{top}" width="{band_w:.1f}" height="{plot_h}" '
            f'class="{pass_class}"/>'
        )
        if idx > 0:
            sep_x = left + (base_event - 0.5) * step
            elems.append(f'<line x1="{sep_x:.1f}" y1="{top}" x2="{sep_x:.1f}" y2="{top + plot_h}" class="separator"/>')

        event_labels = [("B", x_bid), ("S", x_sel), ("O", x_out)]
        for label, x in event_labels:
            elems.append(f'<text x="{x:.1f}" y="{top + plot_h + 20}" text-anchor="middle" class="x-label">{label}</text>')

        outcome = "PASS" if first["team_passed"] else "FAIL"
        problem_label = f"{problem_number}. {first['task']} {outcome}"
        center = (x_bid + x_out) / 2
        elems.append(
            f'<text x="{center:.1f}" y="{top + plot_h + 42}" text-anchor="middle" '
            f'class="x-label">{esc(problem_label)}</text>'
        )
        elems.append(
            f'<text x="{center:.1f}" y="{top + plot_h + 60}" text-anchor="middle" '
            f'class="x-sub">{esc(run_file.replace(".json", ""))}</text>'
        )

        for row in sorted(group, key=lambda r: r["agent"]):
            agent = row["agent"]
            conf = row["confidence"]
            y = y_for(conf)
            agent_class = "agent-c" if agent == AGENT_C_ID else "agent-s"
            selected_class = " selected" if row["selected"] else ""
            bid = row.get("bid", "?")
            conf_label = "?" if conf is None else conf
            points = [
                ("bid", base_event, bid),
                ("selection", base_event + 1, "selected" if row["selected"] else "not selected"),
                ("outcome", base_event + 2, outcome),
            ]
            for event_name, event_index, event_value in points:
                x = x_for(event_index, agent)
                polylines[agent].append((x, y))
                title = (
                    f"{short_agent(agent)} {event_name}: {event_value} | confidence {conf_label}% | "
                    f"problem {problem_number} {first['task']} {outcome} | {row.get('claim') or ''}"
                )
                if event_name == "bid":
                    point_elems.append(
                        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" '
                        f'class="event-point {agent_class}"><title>{esc(title)}</title></circle>'
                    )
                    point_elems.append(
                        f'<text x="{x:.1f}" y="{y - 12:.1f}" text-anchor="middle" '
                        f'class="point-label">{short_agent(agent)}</text>'
                    )
                    if bid == "DEFER":
                        point_elems.append(
                            f'<text x="{x:.1f}" y="{y + 22:.1f}" text-anchor="middle" '
                            f'class="defer-label">DEFER</text>'
                        )
                elif event_name == "selection":
                    point_elems.append(
                        f'<rect x="{x - 7:.1f}" y="{y - 7:.1f}" width="14" height="14" '
                        f'class="event-point {agent_class}{selected_class}"><title>{esc(title)}</title></rect>'
                    )
                else:
                    outcome_class = "outcome-pass" if first["team_passed"] else "outcome-fail"
                    diamond = (
                        f"{x:.1f},{y - 9:.1f} {x + 9:.1f},{y:.1f} "
                        f"{x:.1f},{y + 9:.1f} {x - 9:.1f},{y:.1f}"
                    )
                    point_elems.append(
                        f'<polygon points="{diamond}" class="event-point {outcome_class}{selected_class}">'
                        f'<title>{esc(title)}</title></polygon>'
                    )

    for agent, pts in polylines.items():
        if len(pts) < 2:
            continue
        cls = "line-c" if agent == AGENT_C_ID else "line-s"
        point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        elems.append(f'<polyline points="{point_text}" class="trajectory {cls}"/>')

    elems.extend(point_elems)
    elems.append("</svg>")
    return "\n".join(elems)


def confidence_timeline_svg(rows: list[dict]) -> str:
    groups = group_counts(rows, ["run_file", "problem_number"])
    if not groups:
        return "<p>No pitch rows to plot.</p>"

    group_items = list(groups.items())
    width = max(760, 130 * len(group_items) + 120)
    height = 360
    left = 58
    right = 24
    top = 32
    bottom = 74
    plot_w = width - left - right
    plot_h = height - top - bottom
    step = plot_w / max(1, len(group_items) - 1)

    def x_for(idx: int, agent: str) -> float:
        base = left + idx * step
        return base + (-12 if agent == AGENT_C_ID else 12)

    def y_for(conf: int | None) -> float:
        conf = 0 if conf is None else max(0, min(100, int(conf)))
        return top + (100 - conf) / 100 * plot_h

    elems: list[str] = []
    elems.append(f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">')
    elems.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis"/>')
    elems.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" class="axis"/>'
    )
    for tick in (0, 25, 50, 75, 100):
        y = y_for(tick)
        elems.append(f'<line x1="{left - 5}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        elems.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="tick">{tick}%</text>')

    elems.append(f'<text x="{left}" y="18" class="axis-label">Confidence by problem</text>')

    for idx, ((run_file, problem_number), group) in enumerate(group_items):
        first = group[0]
        x_center = left + idx * step
        pass_class = "pass-band" if first["team_passed"] else "fail-band"
        elems.append(
            f'<rect x="{x_center - 36:.1f}" y="{top}" width="72" height="{plot_h}" '
            f'class="{pass_class}"/>'
        )
        outcome = "PASS" if first["team_passed"] else "FAIL"
        label = f"{problem_number}. {first['task']} {outcome}"
        elems.append(
            f'<text x="{x_center:.1f}" y="{top + plot_h + 22}" text-anchor="middle" '
            f'class="x-label">{esc(label)}</text>'
        )
        elems.append(
            f'<text x="{x_center:.1f}" y="{top + plot_h + 40}" text-anchor="middle" '
            f'class="x-sub">{esc(run_file.replace(".json", ""))}</text>'
        )

        for row in sorted(group, key=lambda r: r["agent"]):
            x = x_for(idx, row["agent"])
            y = y_for(row["confidence"])
            agent_class = "agent-c" if row["agent"] == AGENT_C_ID else "agent-s"
            selected_class = " selected" if row["selected"] else ""
            bid = row.get("bid", "?")
            conf = "?" if row["confidence"] is None else row["confidence"]
            title = (
                f"{short_agent(row['agent'])}: {bid} @ {conf}% | "
                f"selected={bool_text(row['selected'])} | team={outcome} | "
                f"{row.get('claim') or ''}"
            )
            elems.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" '
                f'class="point {agent_class}{selected_class}"><title>{esc(title)}</title></circle>'
            )
            elems.append(
                f'<text x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" '
                f'class="point-label">{short_agent(row["agent"])}</text>'
            )
            if bid == "DEFER":
                elems.append(
                    f'<text x="{x:.1f}" y="{y + 26:.1f}" text-anchor="middle" '
                    f'class="defer-label">DEFER</text>'
                )

    elems.append("</svg>")
    return "\n".join(elems)


def bar_svg(title: str, rows: list[tuple[str, int, int]], *, width: int = 760) -> str:
    height = 260
    left = 54
    right = 24
    top = 44
    bottom = 52
    plot_w = width - left - right
    plot_h = height - top - bottom
    bar_gap = 18
    bar_w = (plot_w - bar_gap * max(0, len(rows) - 1)) / max(1, len(rows))

    elems = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">']
    elems.append(f'<text x="{left}" y="22" class="axis-label">{esc(title)}</text>')
    elems.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis"/>')
    elems.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
        f'y2="{top + plot_h}" class="axis"/>'
    )
    for tick in (0, 50, 100):
        y = top + (100 - tick) / 100 * plot_h
        elems.append(f'<line x1="{left - 5}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        elems.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="tick">{tick}%</text>')

    for idx, (label, numer, denom) in enumerate(rows):
        rate = 0 if denom == 0 else numer / denom
        h = rate * plot_h
        x = left + idx * (bar_w + bar_gap)
        y = top + plot_h - h
        elems.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" class="bar"/>')
        elems.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 7:.1f}" text-anchor="middle" class="bar-label">'
            f'{pct(numer, denom)}</text>'
        )
        elems.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 20}" text-anchor="middle" '
            f'class="x-label">{esc(label)}</text>'
        )
        elems.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + plot_h + 38}" text-anchor="middle" '
            f'class="x-sub">n={denom}</text>'
        )
    elems.append("</svg>")
    return "\n".join(elems)


def leader_pass_by_confidence(rows: list[dict]) -> str:
    leaders = [r for r in rows if r["selected"]]
    grouped = group_counts(leaders, ["confidence_bin"])
    order = ["0-49", "50-69", "70-84", "85-94", "95-100", "unknown"]
    bars = []
    for label in order:
        group = grouped.get((label,), [])
        if not group:
            continue
        bars.append((label, sum(1 for r in group if r["leader_passed"] is True), len(group)))
    return bar_svg("Selected leader pass rate by confidence bin", bars) if bars else "<p>No leaders to plot.</p>"


def lead_rate_by_pressure(rows: list[dict]) -> str:
    bars = []
    for label, predicate in (
        ("behind", lambda r: r["behind_before"] is True),
        ("tied/ahead", lambda r: r["behind_before"] is False),
        ("after fail", lambda r: r["prev_team_failed"] is True),
        ("after no fail", lambda r: r["prev_team_failed"] is False and r["problem_number"] > 1),
    ):
        group = [r for r in rows if predicate(r)]
        bars.append((label, sum(1 for r in group if r["bid"] == "LEAD"), len(group)))
    return bar_svg("LEAD bid rate under score/history pressure", bars)


def agent_table(rows: list[dict]) -> str:
    grouped = group_counts(rows, ["agent"])
    lines = [
        "<table>",
        "<thead><tr><th>Agent</th><th>Rows</th><th>LEAD rate</th><th>Selected</th>"
        "<th>Leader pass</th><th>Avg confidence</th></tr></thead>",
        "<tbody>",
    ]
    for (agent,), group in grouped.items():
        lead = sum(1 for r in group if r["bid"] == "LEAD")
        selected = sum(1 for r in group if r["selected"])
        leader_total = sum(1 for r in group if r["selected"])
        leader_pass = sum(1 for r in group if r["leader_passed"] is True)
        avg_conf = mean([r["confidence"] for r in group])
        avg_conf_text = "n/a" if avg_conf is None else f"{avg_conf:.0f}%"
        lines.append(
            "<tr>"
            f"<td>{esc(agent)}</td>"
            f"<td>{len(group)}</td>"
            f"<td>{pct(lead, len(group))}</td>"
            f"<td>{selected}/{len(group)}</td>"
            f"<td>{leader_pass}/{leader_total}</td>"
            f"<td>{avg_conf_text}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return "\n".join(lines)


def problem_table(rows: list[dict]) -> str:
    groups = group_counts(rows, ["run_file", "problem_number"])
    lines = [
        "<table>",
        "<thead><tr><th>Run</th><th>#</th><th>Task</th><th>Outcome</th><th>Bids</th><th>Selected</th></tr></thead>",
        "<tbody>",
    ]
    for (run_file, problem_number), group in groups.items():
        first = group[0]
        bids = []
        selected = ""
        for row in sorted(group, key=lambda r: r["agent"]):
            marker = "*" if row["selected"] else ""
            bids.append(f"{short_agent(row['agent'])}: {row['bid']} @{row['confidence']}%{marker}")
            if row["selected"]:
                selected = short_agent(row["agent"])
        outcome = "PASS" if first["team_passed"] else "FAIL"
        lines.append(
            "<tr>"
            f"<td>{esc(run_file)}</td>"
            f"<td>{problem_number}</td>"
            f"<td>{esc(first['task'])}</td>"
            f"<td><span class=\"pill {'pass' if first['team_passed'] else 'fail'}\">{outcome}</span></td>"
            f"<td>{esc(' | '.join(bids))}</td>"
            f"<td>{esc(selected)}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return "\n".join(lines)


def render_html(rows: list[dict], run_files: list[Path]) -> str:
    run_names = ", ".join(p.name for p in run_files)
    problem_count = len({problem_key(r) for r in rows})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Behavior Analysis</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --ink: #1e2428;
      --muted: #657078;
      --panel: #ffffff;
      --line: #c9d0d6;
      --grid: #e4e8eb;
      --green: #2d8a57;
      --red: #c65050;
      --blue: #3b6ea8;
      --gold: #b6842d;
    }}
    body {{
      margin: 0;
      padding: 28px;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    h1, h2 {{ margin: 0 0 12px; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 18px; margin-top: 26px; }}
    .meta {{ color: var(--muted); margin-bottom: 18px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid #dde1e4;
      border-radius: 8px;
      padding: 18px;
      margin: 16px 0;
      overflow-x: auto;
    }}
    .chart {{ width: 100%; max-width: 1200px; display: block; }}
    .axis {{ stroke: var(--line); stroke-width: 1.2; }}
    .grid {{ stroke: var(--grid); stroke-width: 1; }}
    .tick, .x-label, .x-sub, .point-label, .bar-label {{ fill: var(--muted); font-size: 12px; }}
    .axis-label {{ fill: var(--ink); font-size: 15px; font-weight: 650; }}
    .x-sub {{ font-size: 10px; }}
    .pass-band {{ fill: #e7f3ec; }}
    .fail-band {{ fill: #f8e8e8; }}
    .separator {{ stroke: #d8dde1; stroke-width: 1; stroke-dasharray: 4 5; }}
    .trajectory {{ fill: none; stroke-width: 2.4; stroke-linejoin: round; stroke-linecap: round; opacity: .82; }}
    .line-c {{ stroke: var(--blue); }}
    .line-s {{ stroke: var(--gold); }}
    .agent-c {{ fill: var(--blue); opacity: .9; }}
    .agent-s {{ fill: var(--gold); opacity: .9; }}
    .selected {{ stroke: #111; stroke-width: 3; }}
    .event-point {{ opacity: .96; }}
    .outcome-pass {{ fill: var(--green); opacity: .9; }}
    .outcome-fail {{ fill: var(--red); opacity: .9; }}
    .defer-label {{ fill: var(--red); font-size: 10px; font-weight: 700; }}
    .bar {{ fill: var(--blue); opacity: .82; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 760px; }}
    th, td {{ border-bottom: 1px solid #e4e8eb; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; color: #fff; font-size: 12px; font-weight: 700; }}
    .pill.pass {{ background: var(--green); }}
    .pill.fail {{ background: var(--red); }}
    .legend {{ display: flex; gap: 18px; flex-wrap: wrap; color: var(--muted); margin: 8px 0 0; }}
    .dot {{ width: 10px; height: 10px; display: inline-block; border-radius: 50%; margin-right: 6px; }}
  </style>
</head>
<body>
  <h1>Behavior Analysis</h1>
  <div class="meta">{len(rows)} agent-bids from {problem_count} problems. Runs: {esc(run_names)}</div>

  <div class="panel">
    <h2>Event Trajectory</h2>
    <div class="legend">
      <span><span class="dot" style="background: var(--blue)"></span>C / code-framed agent</span>
      <span><span class="dot" style="background: var(--gold)"></span>S / SQL-framed agent</span>
      <span>Circle = bid</span>
      <span>Square = selection</span>
      <span>Diamond = outcome</span>
      <span>Black outline = selected leader</span>
      <span>Green/red diamond = pass/fail</span>
    </div>
    {event_trajectory_svg(rows)}
  </div>

  <div class="panel">
    <h2>Confidence by Problem</h2>
    <div class="legend">
      <span><span class="dot" style="background: var(--blue)"></span>C / code-framed agent</span>
      <span><span class="dot" style="background: var(--gold)"></span>S / SQL-framed agent</span>
      <span>Black outline = selected leader</span>
      <span>Green band = pass, red band = fail</span>
    </div>
    {confidence_timeline_svg(rows)}
  </div>

  <div class="panel">
    <h2>Calibration</h2>
    {leader_pass_by_confidence(rows)}
  </div>

  <div class="panel">
    <h2>Pressure</h2>
    {lead_rate_by_pressure(rows)}
  </div>

  <div class="panel">
    <h2>Per-Agent Summary</h2>
    {agent_table(rows)}
  </div>

  <div class="panel">
    <h2>Problem Timeline</h2>
    {problem_table(rows)}
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an HTML/SVG behavior dashboard")
    parser.add_argument("run_file", nargs="+", help="Path or glob, e.g. runs/run_C_*.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/views/behavior_analysis.html"),
        help="HTML output path",
    )
    args = parser.parse_args()

    run_files = resolve_run_files(args.run_file)
    if not run_files:
        print("No run files found.", file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = []
    for run_file in run_files:
        rows.extend(build_rows(run_file))

    if not rows:
        print("No structured behavior rows found.", file=sys.stderr)
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(rows, run_files))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
