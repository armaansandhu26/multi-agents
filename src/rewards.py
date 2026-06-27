"""Reward rules and cumulative score tracking.

Grading is execution-based (src/execution_grading.py); the old LLM grader was
removed because it passed everything (see NEXT_STEPS.md, Step 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agents import AGENT_C_ID, AGENT_S_ID, moderator_label


@dataclass(frozen=True)
class RewardConfig:
    success_both: float = 1.0
    leader_bonus: float = 2.0
    leader_fail_penalty: float = -2.0
    follower_on_fail: float = 0.0


@dataclass
class ScoreBoard:
    scores: dict[str, float] = field(
        default_factory=lambda: {AGENT_C_ID: 0.0, AGENT_S_ID: 0.0}
    )
    history: list[dict] = field(default_factory=list)

    def apply(
        self,
        *,
        leader: str,
        follower: str,
        passed: bool,
        config: RewardConfig,
        problem_id: str,
    ) -> dict:
        if passed:
            leader_delta = config.success_both + config.leader_bonus
            follower_delta = config.success_both
        else:
            leader_delta = config.leader_fail_penalty
            follower_delta = config.follower_on_fail

        self.scores[leader] += leader_delta
        self.scores[follower] += follower_delta

        record = {
            "problem_id": problem_id,
            "leader": leader,
            "follower": follower,
            "passed": passed,
            "leader_delta": leader_delta,
            "follower_delta": follower_delta,
            "scores_after": dict(self.scores),
        }
        self.history.append(record)
        return record

    def to_dict(self) -> dict:
        return {"scores": dict(self.scores), "history": list(self.history)}


def format_reward_message(record: dict, config: RewardConfig) -> str:
    outcome = "SUCCESS" if record["passed"] else "FAILURE"
    return (
        f"Problem {record['problem_id']} — {outcome}\n"
        f"Leader: {moderator_label(record['leader'])} ({record['leader_delta']:+.1f})\n"
        f"Follower: {moderator_label(record['follower'])} ({record['follower_delta']:+.1f})\n"
        f"Cumulative scores — {moderator_label(AGENT_C_ID)}: "
        f"{record['scores_after'][AGENT_C_ID]:.1f}, "
        f"{moderator_label(AGENT_S_ID)}: {record['scores_after'][AGENT_S_ID]:.1f}\n\n"
        f"Reward rules reminder: success → leader +{config.success_both + config.leader_bonus}, "
        f"follower +{config.success_both}; failure → leader {config.leader_fail_penalty}, "
        f"follower {config.follower_on_fail}."
    )
