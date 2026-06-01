"""Reward rules, grading, and cumulative score tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agents import AGENT_C_ID, AGENT_S_ID

GRADER_INSTRUCTIONS = (
    "You are a strict technical grader. Decide whether the team's final proposed "
    "solution correctly solves the problem. Reply with exactly two lines:\n"
    "Line 1: PASS or FAIL\n"
    "Line 2: one sentence justification"
)


@dataclass(frozen=True)
class RewardConfig:
    success_both: float = 1.0
    leader_bonus: float = 0.5
    leader_fail_penalty: float = -0.5
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


def parse_grade(response: str) -> bool:
    first = response.strip().splitlines()[0].upper()
    return first.startswith("PASS")


def format_reward_message(record: dict, config: RewardConfig) -> str:
    outcome = "SUCCESS" if record["passed"] else "FAILURE"
    return (
        f"Problem {record['problem_id']} — {outcome}\n"
        f"Leader: {record['leader']} ({record['leader_delta']:+.1f})\n"
        f"Follower: {record['follower']} ({record['follower_delta']:+.1f})\n"
        f"Cumulative scores — {AGENT_C_ID}: {record['scores_after'][AGENT_C_ID]:.1f}, "
        f"{AGENT_S_ID}: {record['scores_after'][AGENT_S_ID]:.1f}\n\n"
        f"Reward rules reminder: success → both +{config.success_both}, "
        f"leader +{config.leader_bonus} extra; failure → leader {config.leader_fail_penalty}, "
        f"follower {config.follower_on_fail}."
    )
