from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from src.agents import (
    AGENT_C,
    AGENT_C_ID,
    AGENT_S,
    AGENT_S_ID,
    MODERATOR_ID,
    MODERATOR_INSTRUCTIONS,
    Agent,
    agent_instructions,
    domain_agent_for_task,
    discussion_turn_prompt,
    final_answer_prompt,
    moderator_label,
    moderator_history_context,
    moderator_score_context,
    pitch_prompt_for,
    volunteer_prompt_for,
)
from src.client import generate_response, make_client
from src.config import Settings
from src.execution_grading import GradeResult, grade_solution
from src.rewards import (
    RewardConfig,
    ScoreBoard,
    format_reward_message,
)

TaskType = Literal["coding", "sql"]
Condition = Literal["A", "B", "C"]
StarterMode = Literal["pitch", "volunteer", "random", "alternate", "code", "sql"]
TiebreakMode = Literal["random", "domain", "continuity"]
TurnKind = Literal["problem", "volunteer", "pitch", "selection", "reward", "agent", "final"]

TURNS_PER_PROBLEM = 6
PROBLEMS_PER_TASK = 3

TASK_TRANSITION_MESSAGE = (
    "You will now work on a different type of problem. "
    "Your full conversation history is preserved. Here is the next problem:"
)


@dataclass
class ProblemSlot:
    task: TaskType
    problem_index: int


@dataclass
class Turn:
    turn_index: int
    task: TaskType
    problem_index: int
    agent_id: str
    content: str
    kind: TurnKind = "agent"


@dataclass
class ExperimentRun:
    run_id: str
    condition: Condition
    task_order: list[TaskType]
    model: str
    temperature: float
    top_p: float
    max_output_tokens: int
    turns: list[Turn] = field(default_factory=list)
    transcript: list[Turn] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k not in ("turns", "transcript")},
            "turns": [asdict(t) for t in self.turns],
            "transcript": [asdict(t) for t in self.transcript],
        }


def build_problem_schedule(
    condition: Condition, problems_per_task: int = PROBLEMS_PER_TASK
) -> list[ProblemSlot]:
    if condition == "A":
        slots = [ProblemSlot("coding", i) for i in range(problems_per_task)]
        slots += [ProblemSlot("sql", i) for i in range(problems_per_task)]
        return slots
    if condition == "B":
        slots = [ProblemSlot("sql", i) for i in range(problems_per_task)]
        slots += [ProblemSlot("coding", i) for i in range(problems_per_task)]
        return slots
    schedule: list[ProblemSlot] = []
    for i in range(problems_per_task):
        schedule.append(ProblemSlot("coding", i))
        schedule.append(ProblemSlot("sql", i))
    return schedule


def task_order_label(condition: Condition, schedule: list[ProblemSlot]) -> list[TaskType]:
    if condition in ("A", "B"):
        return ["coding", "sql"] if condition == "A" else ["sql", "coding"]
    return [slot.task for slot in schedule]


def load_problems(task: TaskType, *, tier: str | None = None) -> list[dict]:
    path = Path(__file__).resolve().parents[1] / "data" / "problems" / f"{task}.json"
    with path.open() as f:
        problems = json.load(f)
    if tier:
        problems = [p for p in problems if p.get("tier") == tier]
    return problems


def format_problem_message(problem: dict, *, prefix: str | None = None) -> str:
    header = f"Problem ({problem['id']}):\n\n"
    body = problem["prompt"].strip()
    if prefix:
        return f"{prefix}\n\n{header}{body}"
    return f"{header}{body}"


def build_agent_input(transcript: list[Turn], agent_id: str) -> list[dict]:
    messages: list[dict] = []
    for turn in transcript:
        if turn.kind in ("problem", "selection", "reward"):
            messages.append({"type": "message", "role": "user", "content": turn.content})
            continue

        if turn.kind in ("volunteer", "pitch"):
            messages.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"[{turn.kind.title()} — {moderator_label(turn.agent_id)}]: "
                        f"{turn.content}"
                    ),
                }
            )
            continue

        role = "assistant" if turn.agent_id == agent_id else "user"
        messages.append({"type": "message", "role": role, "content": turn.content})
    return messages


def next_speaker(turn_number: int, starter: str) -> str:
    order = [starter, AGENT_S_ID if starter == AGENT_C_ID else AGENT_C_ID]
    return order[(turn_number - 1) % 2]


def parse_volunteer_choice(response: str) -> bool:
    first_line = response.strip().splitlines()[0].upper()
    if first_line.startswith("LEAD"):
        return True
    if first_line.startswith("DEFER"):
        return False
    return "LEAD" in first_line and "DEFER" not in first_line


def parse_pitch_bid(response: str) -> dict:
    """Extract structured bid metadata from the pitch response."""
    bid: str | None = None
    confidence: int | None = None
    claim: str | None = None

    for line in response.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("BID:"):
            value = stripped.split(":", 1)[1].strip().upper()
            if value.startswith("LEAD"):
                bid = "LEAD"
            elif value.startswith("DEFER"):
                bid = "DEFER"
        elif upper.startswith("CONFIDENCE:"):
            value = stripped.split(":", 1)[1]
            match = re.search(r"\d+", value)
            if match:
                confidence = max(0, min(100, int(match.group(0))))
        elif upper.startswith("CLAIM:"):
            claim = stripped.split(":", 1)[1].strip()

    if bid is None:
        first_line = response.strip().splitlines()[0].upper() if response.strip() else ""
        if "DEFER" in first_line and "LEAD" not in first_line:
            bid = "DEFER"
        elif "LEAD" in first_line:
            bid = "LEAD"

    return {
        "bid": bid or "UNKNOWN",
        "wants_lead": bid == "LEAD",
        "confidence": confidence,
        "claim": claim,
    }


def parse_moderator_choice(response: str) -> str:
    label_to_agent = {
        "agent_alpha": AGENT_C_ID,
        "agent_beta": AGENT_S_ID,
        "code_expert": AGENT_C_ID,
        "sql_expert": AGENT_S_ID,
    }
    for line in response.splitlines():
        line_lower = line.lower()
        if "leader" in line_lower:
            match = re.search(
                r"leader\s*:\s*(agent_alpha|agent_beta|code_expert|sql_expert)",
                line_lower,
            )
            if match:
                return label_to_agent[match.group(1)]
    lower = response.lower()
    alpha_pos = lower.rfind("agent_alpha")
    beta_pos = lower.rfind("agent_beta")
    if alpha_pos != -1 or beta_pos != -1:
        return AGENT_S_ID if beta_pos > alpha_pos else AGENT_C_ID
    if "sql_expert" in lower and "code_expert" not in lower:
        return AGENT_S_ID
    if "sql_expert" in lower and "code_expert" in lower:
        return AGENT_S_ID if lower.rfind("sql_expert") > lower.rfind("code_expert") else AGENT_C_ID
    return AGENT_C_ID


def select_starter_from_volunteers(
    task: TaskType,
    volunteers: dict[str, bool],
    rng: random.Random,
    *,
    tiebreak: TiebreakMode = "random",
    previous_starter: str | None = None,
) -> tuple[str, str]:
    domain_agent = domain_agent_for_task(task)
    c_wants = volunteers[AGENT_C_ID]
    s_wants = volunteers[AGENT_S_ID]

    if c_wants and not s_wants:
        return AGENT_C_ID, "only_agent_alpha_volunteered"
    if s_wants and not c_wants:
        return AGENT_S_ID, "only_agent_beta_volunteered"

    if c_wants and s_wants:
        if tiebreak == "domain":
            return domain_agent, "both_volunteered_task_aligned_agent_leads"
        if tiebreak == "continuity" and previous_starter is not None:
            return previous_starter, "both_volunteered_previous_leader_leads"
        chosen = rng.choice([AGENT_C_ID, AGENT_S_ID])
        return chosen, "both_volunteered_random_tiebreak"

    if not c_wants and not s_wants:
        return domain_agent, "both_deferred_domain_expert_leads"

    return domain_agent, "fallback"


def request_final_answer(
    client,
    settings: Settings,
    leader: Agent,
    transcript: list[Turn],
    task: TaskType,
    scores: dict[str, float],
    reward_history: list[dict],
) -> str:
    """The leader compiles the team's final solution after the discussion."""
    messages = build_agent_input(transcript, leader.agent_id)
    messages.append(
        {"type": "message", "role": "user", "content": final_answer_prompt(task)}
    )
    return generate_response(
        client,
        settings,
        instructions=agent_instructions(leader, scores, reward_history),
        input_messages=messages,
    )


def request_pitch(
    client,
    settings: Settings,
    agent: Agent,
    transcript: list[Turn],
    task: TaskType,
    scores: dict[str, float],
    reward_history: list[dict],
) -> str:
    messages = build_agent_input(transcript, agent.agent_id)
    messages.append(
        {"type": "message", "role": "user", "content": pitch_prompt_for(agent, task)}
    )
    return generate_response(
        client,
        settings,
        instructions=agent_instructions(agent, scores, reward_history),
        input_messages=messages,
    )


def run_moderator_selection(
    client,
    settings: Settings,
    problem: dict,
    pitches: dict[str, str],
    scores: dict[str, float],
    reward_history: list[dict],
) -> tuple[str, str]:
    moderator_input = (
        f"Problem ({problem['id']}):\n{problem['prompt']}\n\n"
        f"{moderator_score_context(scores)}\n\n"
        f"{moderator_history_context(reward_history)}\n\n"
        f"Pitch from {moderator_label(AGENT_C_ID)}:\n{pitches[AGENT_C_ID]}\n\n"
        f"Pitch from {moderator_label(AGENT_S_ID)}:\n{pitches[AGENT_S_ID]}"
    )
    response = generate_response(
        client,
        settings,
        instructions=MODERATOR_INSTRUCTIONS,
        input_messages=[{"type": "message", "role": "user", "content": moderator_input}],
    )
    leader = parse_moderator_choice(response)
    return leader, response


def run_pitch_phase(
    client,
    settings: Settings,
    transcript: list[Turn],
    *,
    task: TaskType,
    problem: dict,
    problem_index: int,
    global_turn_index: int,
    scores: dict[str, float],
    reward_history: list[dict],
) -> tuple[str, str, list[Turn], int, dict]:
    phase_turns: list[Turn] = []
    pitches: dict[str, str] = {}
    pitch_bids: dict[str, dict] = {}

    for agent in (AGENT_C, AGENT_S):
        response = request_pitch(
            client, settings, agent, transcript, task, scores, reward_history
        )
        pitches[agent.agent_id] = response
        pitch_bids[agent.agent_id] = parse_pitch_bid(response)
        phase_turns.append(
            Turn(
                turn_index=global_turn_index,
                task=task,
                problem_index=problem_index,
                agent_id=agent.agent_id,
                content=response,
                kind="pitch",
            )
        )
        global_turn_index += 1

    leader, moderator_response = run_moderator_selection(
        client, settings, problem, pitches, scores, reward_history
    )
    follower = AGENT_S_ID if leader == AGENT_C_ID else AGENT_C_ID

    selection_text = (
        f"Moderator selection for {problem['id']}:\n{moderator_response.strip()}\n\n"
        f"{moderator_label(leader)} will open the discussion. "
        f"{moderator_label(follower)} follows.\n"
        "Leader earns +3.0 on team success but -2.0 on team failure; "
        "follower earns +1.0 on team success and 0 on team failure."
    )
    phase_turns.append(
        Turn(
            turn_index=global_turn_index,
            task=task,
            problem_index=problem_index,
            agent_id=MODERATOR_ID,
            content=selection_text,
            kind="selection",
        )
    )
    global_turn_index += 1

    meta = {
        "pitches": pitches,
        "pitch_bids": pitch_bids,
        "moderator_response": moderator_response,
        "starter_agent_id": leader,
        "follower_agent_id": follower,
        "selection_reason": "moderator_pitch_selection",
    }
    return leader, follower, phase_turns, global_turn_index, meta


def request_volunteer(
    client,
    settings: Settings,
    agent: Agent,
    transcript: list[Turn],
    task: TaskType,
    scores: dict[str, float],
    reward_history: list[dict],
) -> str:
    messages = build_agent_input(transcript, agent.agent_id)
    messages.append(
        {"type": "message", "role": "user", "content": volunteer_prompt_for(agent, task)}
    )
    return generate_response(
        client,
        settings,
        instructions=agent_instructions(agent, scores, reward_history),
        input_messages=messages,
    )


def run_volunteer_phase(
    client,
    settings: Settings,
    transcript: list[Turn],
    *,
    task: TaskType,
    problem_index: int,
    global_turn_index: int,
    rng: random.Random,
    scores: dict[str, float],
    reward_history: list[dict],
    tiebreak: TiebreakMode = "random",
    previous_starter: str | None = None,
) -> tuple[str, str, list[Turn], int, dict]:
    volunteer_turns: list[Turn] = []
    bids: dict[str, str] = {}
    wants_lead: dict[str, bool] = {}

    for agent in (AGENT_C, AGENT_S):
        response = request_volunteer(
            client, settings, agent, transcript, task, scores, reward_history
        )
        wants_lead[agent.agent_id] = parse_volunteer_choice(response)
        bids[agent.agent_id] = response
        volunteer_turns.append(
            Turn(
                turn_index=global_turn_index,
                task=task,
                problem_index=problem_index,
                agent_id=agent.agent_id,
                content=response,
                kind="volunteer",
            )
        )
        global_turn_index += 1

    starter, reason = select_starter_from_volunteers(
        task, wants_lead, rng, tiebreak=tiebreak, previous_starter=previous_starter
    )
    follower = AGENT_S_ID if starter == AGENT_C_ID else AGENT_C_ID
    selection_text = (
        f"Volunteer phase complete.\n"
        f"- {moderator_label(AGENT_C_ID)}: {'LEAD' if wants_lead[AGENT_C_ID] else 'DEFER'}\n"
        f"- {moderator_label(AGENT_S_ID)}: {'LEAD' if wants_lead[AGENT_S_ID] else 'DEFER'}\n"
        f"{moderator_label(starter)} will open the discussion ({reason})."
    )
    volunteer_turns.append(
        Turn(
            turn_index=global_turn_index,
            task=task,
            problem_index=problem_index,
            agent_id="system",
            content=selection_text,
            kind="selection",
        )
    )
    global_turn_index += 1

    meta = {
        "volunteer_bids": bids,
        "volunteer_wants_lead": wants_lead,
        "starter_agent_id": starter,
        "follower_agent_id": follower,
        "selection_reason": reason,
    }
    return starter, follower, volunteer_turns, global_turn_index, meta


def choose_problem_starters(
    *,
    num_problems: int,
    mode: StarterMode,
    seed: int | None,
    default_starter: str = AGENT_C_ID,
) -> list[str]:
    rng = random.Random(seed)

    if mode == "code":
        return [AGENT_C_ID] * num_problems
    if mode == "sql":
        return [AGENT_S_ID] * num_problems
    if mode == "alternate":
        starters: list[str] = []
        current = default_starter
        for _ in range(num_problems):
            starters.append(current)
            current = AGENT_S_ID if current == AGENT_C_ID else AGENT_C_ID
        return starters

    return [rng.choice([AGENT_C_ID, AGENT_S_ID]) for _ in range(num_problems)]


def run_experiment(
    settings: Settings,
    *,
    condition: Condition,
    starter_mode: StarterMode = "pitch",
    tiebreak: TiebreakMode = "random",
    seed: int | None = None,
    reward_config: RewardConfig | None = None,
    problems_per_task: int = PROBLEMS_PER_TASK,
    problem_tier: str | None = None,
) -> ExperimentRun:
    schedule = build_problem_schedule(condition, problems_per_task)
    total_problems = len(schedule)

    # Same seed -> same problem sample across conditions A/B/C (comparable sessions).
    problem_rng = random.Random(seed)
    selected_problems: dict[TaskType, list[dict]] = {}
    for task_name in ("coding", "sql"):
        bank = load_problems(task_name, tier=problem_tier)  # type: ignore[arg-type]
        if problems_per_task >= len(bank):
            selected_problems[task_name] = bank
        else:
            selected_problems[task_name] = problem_rng.sample(bank, problems_per_task)
    preset_starters = (
        choose_problem_starters(num_problems=total_problems, mode=starter_mode, seed=seed)
        if starter_mode not in ("volunteer", "pitch")
        else None
    )

    reward_config = reward_config or RewardConfig()
    scoreboard = ScoreBoard()
    starter_plan: list[dict] = []
    problem_counter = 0
    rng = random.Random(seed)

    run = ExperimentRun(
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        condition=condition,
        task_order=task_order_label(condition, schedule),
        model=settings.model,
        temperature=settings.temperature,
        top_p=settings.top_p,
        max_output_tokens=settings.max_output_tokens,
        metadata={
            "starter_mode": starter_mode,
            "tiebreak": tiebreak,
            "seed": seed,
            "grader": "execution",
            "problems_per_task": problems_per_task,
            "problem_tier": problem_tier,
            "reward_config": asdict(reward_config),
            "problem_schedule": [asdict(slot) for slot in schedule],
            "problem_ids": {
                task_name: [p["id"] for p in problems]
                for task_name, problems in selected_problems.items()
            },
            "problem_starters": starter_plan,
            "scoreboard": scoreboard.to_dict(),
        },
    )

    client = make_client(settings)
    transcript: list[Turn] = []
    global_turn_index = 0
    previous_task: TaskType | None = None
    previous_starter: str | None = None
    scores = scoreboard.scores

    for slot in schedule:
        task = slot.task
        problem_idx = slot.problem_index
        problem = selected_problems[task][problem_idx]
        problem_discussion: list[Turn] = []

        prefix = None
        if previous_task is not None and task != previous_task:
            prefix = TASK_TRANSITION_MESSAGE

        problem_message = format_problem_message(problem, prefix=prefix)
        transcript.append(
            Turn(
                turn_index=global_turn_index,
                task=task,
                problem_index=problem_idx,
                agent_id="system",
                content=problem_message,
                kind="problem",
            )
        )
        global_turn_index += 1

        if starter_mode == "pitch":
            starter_agent_id, follower_agent_id, phase_turns, global_turn_index, phase_meta = (
                run_pitch_phase(
                    client,
                    settings,
                    transcript,
                    task=task,
                    problem=problem,
                    problem_index=problem_idx,
                    global_turn_index=global_turn_index,
                    scores=scores,
                    reward_history=scoreboard.history,
                )
            )
            transcript.extend(phase_turns)
            starter_plan.append(
                {
                    "task": task,
                    "problem_index": problem_idx,
                    "problem_id": problem["id"],
                    **phase_meta,
                }
            )
        elif starter_mode == "volunteer":
            starter_agent_id, follower_agent_id, phase_turns, global_turn_index, phase_meta = (
                run_volunteer_phase(
                    client,
                    settings,
                    transcript,
                    task=task,
                    problem_index=problem_idx,
                    global_turn_index=global_turn_index,
                    rng=rng,
                    scores=scores,
                    reward_history=scoreboard.history,
                    tiebreak=tiebreak,
                    previous_starter=previous_starter,
                )
            )
            transcript.extend(phase_turns)
            starter_plan.append(
                {
                    "task": task,
                    "problem_index": problem_idx,
                    "problem_id": problem["id"],
                    **phase_meta,
                }
            )
        else:
            starter_agent_id = preset_starters[problem_counter]
            follower_agent_id = (
                AGENT_S_ID if starter_agent_id == AGENT_C_ID else AGENT_C_ID
            )
            starter_plan.append(
                {
                    "task": task,
                    "problem_index": problem_idx,
                    "problem_id": problem["id"],
                    "starter_agent_id": starter_agent_id,
                    "follower_agent_id": follower_agent_id,
                }
            )
            problem_counter += 1

        for turn_in_problem in range(1, TURNS_PER_PROBLEM + 1):
            speaker_id = next_speaker(turn_in_problem, starter_agent_id)
            agent: Agent = AGENT_C if speaker_id == AGENT_C_ID else AGENT_S

            response_text = generate_response(
                client,
                settings,
                instructions=agent_instructions(agent, scores, scoreboard.history),
                input_messages=[
                    *build_agent_input(transcript, speaker_id),
                    {
                        "type": "message",
                        "role": "user",
                        "content": discussion_turn_prompt(
                            task=task,
                            turn_in_problem=turn_in_problem,
                            is_leader=speaker_id == starter_agent_id,
                        ),
                    },
                ],
            )

            turn = Turn(
                turn_index=global_turn_index,
                task=task,
                problem_index=problem_idx,
                agent_id=speaker_id,
                content=response_text,
                kind="agent",
            )
            transcript.append(turn)
            run.turns.append(turn)
            problem_discussion.append(turn)
            global_turn_index += 1

        if starter_mode == "pitch":
            leader_agent = AGENT_C if starter_agent_id == AGENT_C_ID else AGENT_S
            final_text = request_final_answer(
                client,
                settings,
                leader_agent,
                transcript,
                task,
                scores,
                scoreboard.history,
            )
            final_turn = Turn(
                turn_index=global_turn_index,
                task=task,
                problem_index=problem_idx,
                agent_id=starter_agent_id,
                content=final_text,
                kind="final",
            )
            transcript.append(final_turn)
            global_turn_index += 1

            grade: GradeResult = grade_solution(problem, task, final_text)
            reward_record = scoreboard.apply(
                leader=starter_agent_id,
                follower=follower_agent_id,
                passed=grade.passed,
                config=reward_config,
                problem_id=problem["id"],
            )
            reward_record["grade_detail"] = grade.detail
            if "pitch_bids" in starter_plan[-1]:
                reward_record["leader_bid"] = starter_plan[-1]["pitch_bids"].get(
                    starter_agent_id, {}
                )
                reward_record["follower_bid"] = starter_plan[-1]["pitch_bids"].get(
                    follower_agent_id, {}
                )
            starter_plan[-1]["passed"] = grade.passed
            starter_plan[-1]["grade_detail"] = grade.detail
            starter_plan[-1]["final_solution"] = final_text
            starter_plan[-1]["extracted_solution"] = grade.extracted_solution
            starter_plan[-1]["reward"] = reward_record

            reward_turn = Turn(
                turn_index=global_turn_index,
                task=task,
                problem_index=problem_idx,
                agent_id="system",
                content=format_reward_message(reward_record, reward_config),
                kind="reward",
            )
            transcript.append(reward_turn)
            global_turn_index += 1
            scores = scoreboard.scores

        previous_task = task
        previous_starter = starter_agent_id

    run.metadata["scoreboard"] = scoreboard.to_dict()
    run.transcript = list(transcript)
    return run


def save_run(run: ExperimentRun, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or Path("runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"run_{run.condition}_{run.run_id}.json"
    with path.open("w") as f:
        json.dump(run.to_dict(), f, indent=2)
    return path
