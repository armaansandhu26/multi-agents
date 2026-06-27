"""Solution-provenance anchoring metric (Step 2 of NEXT_STEPS.md).

Anchoring operationalized directly: whose FIRST proposal does the team's FINAL
graded solution most resemble? The agent whose initial idea survived the
discussion is the anchor for that problem.

This replaces adjacent-turn lexical overlap as the primary measure. Two
similarity signals are combined:
- TF-IDF cosine (real IDF, computed over all turns in the run) — robust to
  shared problem vocabulary dominating the score.
- Token-sequence ratio (difflib) — sensitive to structural/code similarity.

Requires runs produced by the Phase 3 harness (kind="final" turns).
"""

from __future__ import annotations

import math
from collections import Counter
from difflib import SequenceMatcher

from src.agents import AGENT_C_ID, AGENT_S_ID
from src.execution_grading import extract_code_blocks
from src.metrics import tokenize

AGENT_IDS = [AGENT_C_ID, AGENT_S_ID]


def solution_content(text: str) -> str:
    """Prefer fenced code blocks (the substantive proposal); fall back to full text."""
    blocks = extract_code_blocks(text)
    if blocks:
        return "\n\n".join(body for _, body in blocks)
    return text


def build_idf(documents: list[str]) -> dict[str, float]:
    n_docs = len(documents)
    doc_freq: Counter = Counter()
    for doc in documents:
        doc_freq.update(set(tokenize(doc)))
    return {
        token: math.log((1 + n_docs) / (1 + df)) + 1.0
        for token, df in doc_freq.items()
    }


def tfidf_cosine(a: str, b: str, idf: dict[str, float]) -> float:
    def vector(text: str) -> dict[str, float]:
        counts = Counter(tokenize(text))
        total = sum(counts.values()) or 1
        return {t: (c / total) * idf.get(t, 1.0) for t, c in counts.items()}

    va, vb = vector(a), vector(b)
    if not va or not vb:
        return 0.0
    dot = sum(va[t] * vb[t] for t in set(va) & set(vb))
    norm = math.sqrt(sum(v * v for v in va.values())) * math.sqrt(
        sum(v * v for v in vb.values())
    )
    return dot / norm if norm else 0.0


def sequence_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, tokenize(a), tokenize(b), autojunk=False).ratio()


def _group_problems(transcript: list[dict]) -> list[dict]:
    """Group transcript turns into problems, keyed by (task, problem_index)."""
    problems: dict[tuple, dict] = {}
    for turn in transcript:
        key = (turn["task"], turn["problem_index"])
        entry = problems.setdefault(
            key, {"task": turn["task"], "problem_index": turn["problem_index"],
                  "agent_turns": [], "final": None}
        )
        kind = turn.get("kind", "agent")
        if kind == "agent":
            entry["agent_turns"].append(turn)
        elif kind == "final":
            entry["final"] = turn
    return list(problems.values())


def compute_provenance(run: dict) -> dict:
    transcript = run.get("transcript") or run.get("turns", [])
    problems = _group_problems(transcript)

    corpus = [
        solution_content(t["content"])
        for t in transcript
        if t.get("kind", "agent") in ("agent", "final")
    ]
    idf = build_idf(corpus)

    leaders = {}
    for item in run.get("metadata", {}).get("problem_starters", []):
        leaders[(item["task"], item["problem_index"])] = item.get("starter_agent_id")

    per_problem = []
    for entry in problems:
        if entry["final"] is None or not entry["agent_turns"]:
            continue

        final_text = solution_content(entry["final"]["content"])
        scores = {}
        for agent_id in AGENT_IDS:
            agent_turns = [t for t in entry["agent_turns"] if t["agent_id"] == agent_id]
            if not agent_turns:
                continue
            first_proposal = solution_content(agent_turns[0]["content"])
            tfidf = tfidf_cosine(final_text, first_proposal, idf)
            seq = sequence_ratio(final_text, first_proposal)
            scores[agent_id] = {
                "tfidf_cosine": tfidf,
                "sequence_ratio": seq,
                "combined": (tfidf + seq) / 2,
            }

        if len(scores) < 2:
            continue

        winner = max(scores.items(), key=lambda kv: kv[1]["combined"])[0]
        loser = AGENT_S_ID if winner == AGENT_C_ID else AGENT_C_ID
        margin = scores[winner]["combined"] - scores[loser]["combined"]
        leader = leaders.get((entry["task"], entry["problem_index"]))
        per_problem.append(
            {
                "task": entry["task"],
                "problem_index": entry["problem_index"],
                "scores": scores,
                "provenance_winner": winner,
                "margin": margin,
                "leader": leader,
                "winner_is_leader": (winner == leader) if leader else None,
            }
        )

    by_task: dict[str, dict] = {}
    for task in sorted({p["task"] for p in per_problem}):
        task_problems = [p for p in per_problem if p["task"] == task]
        wins = Counter(p["provenance_winner"] for p in task_problems)
        mean_combined = {
            agent: sum(p["scores"][agent]["combined"] for p in task_problems)
            / len(task_problems)
            for agent in AGENT_IDS
        }
        by_task[task] = {
            "n_problems": len(task_problems),
            "wins": dict(wins),
            "mean_combined": mean_combined,
            "anchor": max(mean_combined, key=mean_combined.get),
        }

    anchors = {task: stats["anchor"] for task, stats in by_task.items()}
    flip_detected = len(set(anchors.values())) > 1 if len(anchors) >= 2 else False

    return {
        "n_problems_scored": len(per_problem),
        "per_problem": per_problem,
        "by_task": by_task,
        "flip": {"flip_detected": flip_detected, "anchors": anchors},
    }
