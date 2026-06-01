from dataclasses import dataclass

AGENT_C_ID = "code_expert"
AGENT_S_ID = "sql_expert"
MODERATOR_ID = "moderator"

SYSTEM_PROMPT_C = (
    "You are a senior software engineer with deep expertise in algorithms and Python. "
    "When a problem involves code, algorithms, or Python, you are the primary authority on this team. "
    "Your collaborator has a database background. "
    "Engage substantively, propose solutions, critique your partner's work, and refine ideas together. "
    "Your goal is correctness."
)

SYSTEM_PROMPT_S = (
    "You are a senior database engineer with deep expertise in SQL and relational schema design. "
    "When a problem involves SQL, databases, or schema design, you are the primary authority on this team. "
    "Your collaborator has a software engineering background. "
    "Engage substantively, propose solutions, critique your partner's work, and refine ideas together. "
    "Your goal is correctness."
)

MODERATOR_INSTRUCTIONS = (
    "You are an impartial moderator selecting which agent leads a collaborative problem-solving round.\n\n"
    "Agents know the reward rules:\n"
    "- Team success: both earn +1.0; the leader earns an additional +0.5\n"
    "- Team failure: the leader loses 0.5; the follower earns 0\n\n"
    "Read the problem and both agents' pitches (submitted privately, before collaboration). "
    "Select who should lead based on domain fit, pitch quality, likelihood of success, "
    "and whether a pitch shows appropriate caution on off-domain problems.\n\n"
    "Reply with exactly two lines:\n"
    "Line 1: LEADER: code_expert OR LEADER: sql_expert\n"
    "Line 2: one sentence rationale"
)

COLLABORATION_NOTE = (
    "You are in a two-agent collaboration. Your own prior messages appear as assistant messages; "
    "your collaborator's messages appear as user messages. "
    "Do not simply agree. If your partner's solution is wrong or incomplete, critique it explicitly "
    "and propose a corrected approach. Avoid repeating the same answer without adding new reasoning."
)

REWARD_RULES_TEXT = (
    "Reward rules for each problem:\n"
    "- Team success: both agents +1.0; leader gets an extra +0.5\n"
    "- Team failure: leader -0.5; follower 0\n"
    "Leading is higher reward but higher risk."
)

PITCH_PROMPT = (
    "Bid to lead this problem. Your collaborator is pitching separately — you have not seen their pitch.\n\n"
    f"{REWARD_RULES_TEXT}\n\n"
    "Write a pitch in 3-5 sentences: why you should (or should not) lead, your approach, and risks. "
    "It is acceptable to pitch deferral if the problem is outside your domain.\n\n"
    "Reply with:\n"
    "Line 1: PITCH\n"
    "Line 2+: your pitch"
)

VOLUNTEER_PROMPT_BASE = (
    "Review the problem above before your collaborator speaks. "
    "Decide whether you should take the lead on this problem.\n"
    "Bid LEAD if the problem is primarily in your domain of authority.\n"
    "Bid DEFER if the problem is primarily in your collaborator's domain and they should open "
    "unless you see a clear error.\n"
    "Reply with exactly two lines:\n"
    "Line 1: LEAD or DEFER\n"
    "Line 2: one sentence explaining your choice from your domain perspective."
)


@dataclass(frozen=True)
class Agent:
    agent_id: str
    display_name: str
    system_prompt: str


AGENT_C = Agent(AGENT_C_ID, "Agent C (code-expert)", SYSTEM_PROMPT_C)
AGENT_S = Agent(AGENT_S_ID, "Agent S (sql-expert)", SYSTEM_PROMPT_S)

AGENTS = {AGENT_C_ID: AGENT_C, AGENT_S_ID: AGENT_S}


def score_context(scores: dict[str, float]) -> str:
    return (
        f"Cumulative scores — {AGENT_C_ID}: {scores.get(AGENT_C_ID, 0):.1f}, "
        f"{AGENT_S_ID}: {scores.get(AGENT_S_ID, 0):.1f}.\n"
        f"{REWARD_RULES_TEXT}"
    )


def agent_instructions(agent: Agent, scores: dict[str, float] | None = None) -> str:
    parts = [agent.system_prompt, COLLABORATION_NOTE]
    if scores is not None:
        parts.append(score_context(scores))
    return "\n\n".join(parts)


def domain_agent_for_task(task: str) -> str:
    return AGENT_C_ID if task == "coding" else AGENT_S_ID


def volunteer_prompt_for(agent: Agent, task: str) -> str:
    if agent.agent_id == domain_agent_for_task(task):
        domain_note = "This problem type is in your primary domain."
    else:
        domain_note = "This problem type is outside your primary domain."
    return f"{VOLUNTEER_PROMPT_BASE}\n{domain_note}"


def pitch_prompt_for(agent: Agent, task: str) -> str:
    if agent.agent_id == domain_agent_for_task(task):
        domain_note = "This problem type is in your primary domain."
    else:
        domain_note = "This problem type is outside your primary domain — consider pitching deferral."
    return f"{PITCH_PROMPT}\n{domain_note}"
