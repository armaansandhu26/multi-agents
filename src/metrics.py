"""
LEGACY lexical-overlap influence metric (secondary measure only).

Inspired by Parfenova, Denzler & Pfeffer (2025). Emergent Convergence in
Multi-Agent LLM Annotation. BlackboxNLP 2025.
https://aclanthology.org/2025.blackboxnlp-1.12/

NOTE (Step 2 of NEXT_STEPS.md): this computes plain term-frequency cosine
between adjacent turns (no IDF, despite what earlier docs claimed). It mostly
measures topical overlap/echoing, not influence direction. The primary
anchoring measure is now solution provenance (src/provenance.py); keep this
only as a secondary/diagnostic signal.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def tf_vector(tokens: Iterable[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {token: count / total for token, count in counts.items()}


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class InfluenceResult:
    influence: dict[str, dict[str, float]]
    anchor_scores: dict[str, float]
    absorber_scores: dict[str, float]
    by_task: dict[str, dict[str, dict[str, float]]]

    def to_dict(self) -> dict:
        return {
            "influence": self.influence,
            "anchor_scores": self.anchor_scores,
            "absorber_scores": self.absorber_scores,
            "by_task": self.by_task,
        }


def compute_influence(turns: list[dict], agent_ids: list[str]) -> InfluenceResult:
    """
    For each adjacent agent-turn pair (source at t-1, target at t), compute
    term-frequency cosine similarity and accumulate I(source -> target).
    """
    overall: dict[str, dict[str, list[float]]] = {
        src: {tgt: [] for tgt in agent_ids} for src in agent_ids
    }
    by_task: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: {src: {tgt: [] for tgt in agent_ids} for src in agent_ids}
    )

    agent_turns = [t for t in turns if t.get("kind", "agent") == "agent"]
    for prev, curr in zip(agent_turns, agent_turns[1:]):
        source = prev["agent_id"]
        target = curr["agent_id"]
        if source == target:
            continue

        sim = cosine_similarity(
            tf_vector(tokenize(prev["content"])),
            tf_vector(tokenize(curr["content"])),
        )
        overall[source][target].append(sim)
        by_task[curr["task"]][source][target].append(sim)

    def average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    influence = {
        src: {tgt: average(scores) for tgt, scores in targets.items()}
        for src, targets in overall.items()
    }
    by_task_avg = {
        task: {
            src: {tgt: average(scores) for tgt, scores in targets.items()}
            for src, targets in task_matrix.items()
        }
        for task, task_matrix in by_task.items()
    }

    anchor_scores = {
        agent: sum(influence[agent].values()) for agent in agent_ids
    }
    absorber_scores = {
        agent: sum(influence[src][agent] for src in agent_ids if src != agent)
        for agent in agent_ids
    }

    return InfluenceResult(
        influence=influence,
        anchor_scores=anchor_scores,
        absorber_scores=absorber_scores,
        by_task=by_task_avg,
    )


def classify_roles(
    anchor_scores: dict[str, float],
    absorber_scores: dict[str, float],
) -> dict[str, str]:
    if not anchor_scores:
        return {}

    top_anchor = max(anchor_scores, key=anchor_scores.get)
    top_absorber = max(absorber_scores, key=absorber_scores.get)
    return {
        agent: (
            "anchor"
            if agent == top_anchor and anchor_scores[agent] > absorber_scores[agent]
            else "absorber"
            if agent == top_absorber and absorber_scores[agent] > anchor_scores[agent]
            else "mixed"
        )
        for agent in anchor_scores
    }


def detect_task_flip(by_task: dict[str, dict[str, dict[str, float]]], agents: list[str]) -> dict:
    """Check whether dominant influence direction reverses across tasks."""
    if len(agents) != 2 or len(by_task) < 2:
        return {"flip_detected": False, "reason": "need two agents and two tasks"}

    a, b = agents
    task_deltas = {}
    for task, matrix in by_task.items():
        i_a_to_b = matrix.get(a, {}).get(b, 0.0)
        i_b_to_a = matrix.get(b, {}).get(a, 0.0)
        task_deltas[task] = {
            f"I({a}->{b})": i_a_to_b,
            f"I({b}->{a})": i_b_to_a,
            "dominant": a if i_a_to_b > i_b_to_a else b,
        }

    tasks = list(task_deltas.keys())
    flip = task_deltas[tasks[0]]["dominant"] != task_deltas[tasks[1]]["dominant"]
    return {"flip_detected": flip, "by_task": task_deltas}
