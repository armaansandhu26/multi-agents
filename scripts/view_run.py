#!/usr/bin/env python3
"""Generate a chat-style HTML viewer for an experiment run."""

from __future__ import annotations

import argparse
import html
import json
import re
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENT_LABELS = {
    "code_expert": "Code Expert (C)",
    "sql_expert": "SQL Expert (S)",
    "moderator": "Moderator",
    "system": "System",
}

AGENT_CLASS = {
    "code_expert": "code",
    "sql_expert": "sql",
    "moderator": "moderator",
    "system": "system",
}


def resolve_run_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        path = Path(pattern)
        if path.is_file():
            candidates = [path]
        else:
            parent = path.parent if path.parent != Path(".") else ROOT / "runs"
            glob_pattern = path.name if path.name else "run_*.json"
            candidates = sorted(parent.glob(glob_pattern))
        files.extend(
            p
            for p in candidates
            if p.is_file()
            and not p.name.endswith("_analysis.json")
            and p.suffix == ".json"
            and p.name.startswith("run_")
        )
    return files


def format_content(text: str) -> str:
    if not text.strip():
        return '<p class="empty">(empty message)</p>'

    escaped = html.escape(text)
    parts: list[str] = []
    pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    last = 0
    for match in pattern.finditer(escaped):
        before = escaped[last : match.start()]
        if before.strip():
            parts.append(f'<div class="text">{_paragraphs(before)}</div>')
        lang = match.group(1)
        code = match.group(2)
        lang_class = f' class="lang-{lang}"' if lang else ""
        parts.append(f"<pre{lang_class}><code>{code}</code></pre>")
        last = match.end()
    tail = escaped[last:]
    if tail.strip():
        parts.append(f'<div class="text">{_paragraphs(tail)}</div>')
    return "".join(parts) if parts else f'<div class="text">{_paragraphs(escaped)}</div>'


def _paragraphs(text: str) -> str:
    chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not chunks:
        chunks = [line for line in text.splitlines() if line.strip()]
    return "".join(f"<p>{chunk.replace(chr(10), '<br>')}</p>" for chunk in chunks)


def group_problems(transcript: list[dict]) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None

    for turn in transcript:
        kind = turn.get("kind", "agent")
        if kind == "problem":
            if current:
                groups.append(current)
            current = {
                "task": turn["task"],
                "problem_index": turn["problem_index"],
                "problem_turn": turn,
                "pitches": [],
                "selection": None,
                "chat": [],
                "reward": None,
            }
            continue

        if current is None:
            continue

        if kind in ("volunteer", "pitch"):
            current["pitches"].append(turn)
        elif kind == "selection":
            current["selection"] = turn
        elif kind == "reward":
            current["reward"] = turn
        elif kind == "agent":
            current["chat"].append(turn)

    if current:
        groups.append(current)
    return groups


def problem_title(problem_turn: dict) -> str:
    content = problem_turn.get("content", "")
    match = re.search(r"Problem \(([^)]+)\)", content)
    return match.group(1) if match else f"{problem_turn['task']} #{problem_turn['problem_index']}"


def render_pitches(pitches: list[dict]) -> str:
    if not pitches:
        return ""
    kind = pitches[0].get("kind", "pitch")
    label = "Pitches" if kind == "pitch" else "Volunteer bids"
    cards = []
    for p in pitches:
        agent = p["agent_id"]
        cards.append(
            f"""
            <div class="pitch-card {AGENT_CLASS.get(agent, 'system')}">
              <div class="pitch-header">{html.escape(AGENT_LABELS.get(agent, agent))}</div>
              <div class="pitch-body">{format_content(p.get('content', ''))}</div>
            </div>
            """
        )
    return f'<div class="phase-label">{label}</div><div class="pitch-row">{"".join(cards)}</div>'


def render_selection(selection: dict | None) -> str:
    if not selection:
        return ""
    return f"""
    <div class="selection-banner">
      <div class="phase-label">Leader selected</div>
      <div class="selection-body">{format_content(selection.get('content', ''))}</div>
    </div>
    """


def render_chat(chat: list[dict], leader: str | None) -> str:
    if not chat:
        return '<div class="phase-label">Discussion</div><p class="empty">No discussion turns.</p>'

    bubbles = ['<div class="phase-label">Discussion</div><div class="chat-thread">']
    for i, turn in enumerate(chat, start=1):
        agent = turn["agent_id"]
        side = AGENT_CLASS.get(agent, "system")
        role_note = " (leader)" if leader and agent == leader and i == 1 else ""
        bubbles.append(
            f"""
            <div class="bubble-row {side}">
              <div class="bubble {side}">
                <div class="bubble-meta">
                  Turn {i} · {html.escape(AGENT_LABELS.get(agent, agent))}{role_note}
                </div>
                <div class="bubble-content">{format_content(turn.get('content', ''))}</div>
              </div>
            </div>
            """
        )
    bubbles.append("</div>")
    return "".join(bubbles)


def render_reward(reward: dict | None) -> str:
    if not reward:
        return ""
    content = reward.get("content", "")
    css = "reward-pass" if "SUCCESS" in content else "reward-fail" if "FAILURE" in content else "reward"
    return f"""
    <div class="reward-banner {css}">
      <div class="phase-label">Outcome</div>
      <div class="reward-body">{format_content(content)}</div>
    </div>
    """


def leader_from_selection(selection: dict | None) -> str | None:
    if not selection:
        return None
    content = selection.get("content", "").lower()
    if "code_expert will open" in content or "leader: code_expert" in content:
        return "code_expert"
    if "sql_expert will open" in content or "leader: sql_expert" in content:
        return "sql_expert"
    if "code_expert" in content and "sql_expert" not in content.split("will open")[0]:
        return "code_expert"
    if "sql_expert" in content:
        return "sql_expert"
    return None


def render_run(run: dict) -> str:
    meta = run.get("metadata", {})
    transcript = run.get("transcript", [])
    groups = group_problems(transcript)
    scoreboard = meta.get("scoreboard", {}).get("scores", {})

    problem_sections = []
    for n, group in enumerate(groups, start=1):
        title = problem_title(group["problem_turn"])
        leader = leader_from_selection(group["selection"])
        leader_label = AGENT_LABELS.get(leader, "—") if leader else "—"

        problem_sections.append(
            f"""
            <section class="problem-block">
              <div class="problem-header">
                <span class="problem-num">Problem {n}</span>
                <span class="problem-tag task-{group['task']}">{group['task'].upper()}</span>
                <span class="problem-id">{html.escape(title)}</span>
                <span class="problem-leader">Leader: {html.escape(leader_label)}</span>
              </div>
              <div class="problem-statement">
                <div class="phase-label">Problem statement</div>
                {format_content(group['problem_turn'].get('content', ''))}
              </div>
              {render_pitches(group['pitches'])}
              {render_selection(group['selection'])}
              {render_chat(group['chat'], leader)}
              {render_reward(group['reward'])}
            </section>
            """
        )

    scores_html = ""
    if scoreboard:
        scores_html = (
            "<div class='scores'>"
            f"<span>C: {scoreboard.get('code_expert', 0):.1f}</span>"
            f"<span>S: {scoreboard.get('sql_expert', 0):.1f}</span>"
            "</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Run {html.escape(run.get('run_id', ''))} — Condition {html.escape(run.get('condition', ''))}</title>
  <style>
    :root {{
      --bg: #0f1117;
      --panel: #171a22;
      --border: #2a3040;
      --text: #e8eaef;
      --muted: #9aa3b2;
      --code-bg: #0b0d12;
      --coding: #6ea8fe;
      --sql: #63e6be;
      --system: #adb5bd;
      --pass: #51cf66;
      --fail: #ff6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .page {{
      max-width: 920px;
      margin: 0 auto;
      padding: 24px 16px 64px;
    }}
    header {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    header h1 {{ margin: 0 0 8px; font-size: 1.4rem; }}
    header .meta {{ color: var(--muted); font-size: 0.9rem; }}
    .scores {{ display: flex; gap: 16px; margin-top: 12px; font-weight: 600; }}
    .problem-block {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 28px;
      overflow: hidden;
    }}
    .problem-header {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      padding: 14px 18px;
      background: #1e2433;
      border-bottom: 1px solid var(--border);
    }}
    .problem-num {{ font-weight: 700; }}
    .problem-tag {{
      font-size: 0.75rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 999px;
      letter-spacing: 0.04em;
    }}
    .task-coding {{ background: #1c3a5f; color: var(--coding); }}
    .task-sql {{ background: #1a4038; color: var(--sql); }}
    .problem-id {{ color: var(--muted); flex: 1; }}
    .problem-leader {{ font-size: 0.85rem; color: var(--muted); }}
    .phase-label {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 8px;
      font-weight: 700;
    }}
    .problem-statement, .pitch-row, .selection-banner, .chat-thread, .reward-banner {{
      padding: 16px 18px;
    }}
    .problem-statement {{ border-bottom: 1px solid var(--border); }}
    .pitch-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      border-bottom: 1px solid var(--border);
    }}
    @media (max-width: 700px) {{ .pitch-row {{ grid-template-columns: 1fr; }} }}
    .pitch-card {{
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }}
    .pitch-card.code {{ border-color: #31527a; }}
    .pitch-card.sql {{ border-color: #2a5c4f; }}
    .pitch-header {{
      padding: 8px 12px;
      font-size: 0.8rem;
      font-weight: 700;
      background: #1a1f2b;
    }}
    .pitch-card.code .pitch-header {{ color: var(--coding); }}
    .pitch-card.sql .pitch-header {{ color: var(--sql); }}
    .pitch-body {{ padding: 12px; font-size: 0.92rem; }}
    .selection-banner {{
      background: #1a1f2b;
      border-bottom: 1px solid var(--border);
    }}
    .selection-body {{ font-size: 0.95rem; }}
    .chat-thread {{ display: flex; flex-direction: column; gap: 12px; }}
    .bubble-row {{ display: flex; }}
    .bubble-row.code {{ justify-content: flex-start; }}
    .bubble-row.sql {{ justify-content: flex-end; }}
    .bubble {{
      max-width: 88%;
      border-radius: 14px;
      padding: 10px 14px;
      border: 1px solid var(--border);
    }}
    .bubble.code {{ background: #152238; border-color: #2d4a73; }}
    .bubble.sql {{ background: #142821; border-color: #2a5c4f; }}
    .bubble-meta {{
      font-size: 0.72rem;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .bubble-content {{ font-size: 0.93rem; }}
    .reward-banner {{ border-top: 1px solid var(--border); }}
    .reward-pass {{ background: #142318; }}
    .reward-fail {{ background: #2a1518; }}
    .reward-pass .phase-label {{ color: var(--pass); }}
    .reward-fail .phase-label {{ color: var(--fail); }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      overflow-x: auto;
      font-size: 0.82rem;
      margin: 8px 0;
    }}
    .text p {{ margin: 0 0 8px; }}
    .empty {{ color: var(--muted); font-style: italic; }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <h1>Condition {html.escape(str(run.get('condition', '')))} · Run {html.escape(str(run.get('run_id', '')))}</h1>
      <div class="meta">
        Model: {html.escape(str(run.get('model', '')))} ·
        Mode: {html.escape(str(meta.get('starter_mode', '?')))} ·
        Order: {' → '.join(html.escape(str(t)) for t in run.get('task_order', []))}
      </div>
      {scores_html}
    </header>
    {''.join(problem_sections)}
  </div>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chat-style HTML viewer for experiment runs")
    parser.add_argument("run_file", nargs="+", help="Run JSON path or glob")
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=ROOT / "runs" / "views",
        help="Directory for HTML output (default: runs/views/)",
    )
    parser.add_argument("--open", action="store_true", help="Open the first generated file in a browser")
    args = parser.parse_args()

    run_files = resolve_run_files(args.run_file)
    if not run_files:
        raise SystemExit("No run files found.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for run_file in run_files:
        with run_file.open() as f:
            run = json.load(f)
        html_doc = render_run(run)
        out_path = args.output_dir / f"view_{run_file.stem}.html"
        out_path.write_text(html_doc, encoding="utf-8")
        generated.append(out_path)
        print(f"Wrote {out_path}")

    if args.open and generated:
        webbrowser.open(generated[0].resolve().as_uri())


if __name__ == "__main__":
    main()
