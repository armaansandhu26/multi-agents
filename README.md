# Multi-agent anchoring experiment

Does claimed domain authority (via system prompt) determine which agent **anchors** during multi-agent collaboration?

Inspired by the **anchor–absorber** framework from:

> Parfenova, Denzler & Pfeffer (2025). *Emergent Convergence in Multi-Agent LLM Annotation.* BlackboxNLP 2025.  
> [PDF](https://aclanthology.org/2025.blackboxnlp-1.12.pdf)

---

## Hypotheses

| ID | Claim |
|---|---|
| **H1** | Domain expert anchors on their task; anchor role **flips** at task boundary (coding ↔ SQL) |
| **H2** | Session **anchor takeover** — one agent dominates leadership/influence across domains over time |
| **H0** | Anchoring is independent of claimed expertise (first speaker, task order, or interaction history drive it) |

---

## Phase 1 — Completed pilots (do not use for main analysis)

These runs validated infrastructure and surfaced design issues. They used **volunteer/LEAD-DEFER** or fixed starters — **not** the current pitch/reward protocol.

### Where to find runs

All logs live in [`runs/`](runs/). Analysis sidecars are `*_analysis.json`.

| File | Condition | Protocol | Seed | View |
|---|---|---|---|---|
| [`run_A_20260601T171051Z.json`](runs/run_A_20260601T171051Z.json) | A | Fixed starter (C first), easy problems | — | [HTML](runs/views/view_run_A_20260601T171051Z.html) |
| [`run_A_20260601T172823Z.json`](runs/run_A_20260601T172823Z.json) | A | Random starter, harder problems | 42 | — |
| [`run_B_20260601T173036Z.json`](runs/run_B_20260601T173036Z.json) | B | Random starter, harder problems | 42 | [HTML](runs/views/view_run_B_20260601T173036Z.html) |
| [`run_A_20260601T175321Z.json`](runs/run_A_20260601T175321Z.json) | A | Volunteer + domain tie-break, stronger prompts | 42 | [HTML](runs/views/view_run_A_20260601T175321Z.html) |
| [`baseline_single_agent.json`](runs/baseline_single_agent.json) | — | Single-agent difficulty check | — | — |

Generate a viewer for any run: `python scripts/view_run.py runs/<file>.json`

Re-analyze any run:

```bash
python scripts/analyze_run.py runs/run_A_20260601T172823Z.json
python scripts/manipulation_check.py runs/run_A_20260601T175321Z.json
```

### What Phase 1 showed

**Infrastructure**
- Azure Foundry + `gpt-5.4-mini` works (`scripts/smoke_test.py`)
- Logging, alternation, task transitions, and cross-condition order (A/B) all work

**Baseline (`baseline_single_agent.json`)**
- Original easy problems: ~100% solo success on both task types (too easy)
- Harder set (`HumanEval/43,54,65` + `spider_hard_*`): solo agent produces plausible solutions on all 6; LLM grader not yet applied to baseline

**Pilot 1** (`run_A_20260601T171051Z`) — easy problems, C always starts
- Pattern: propose → validate → echo (no real debate)
- **C anchored both coding and SQL**; H1 flip: **no**
- Bug: `[You]`/`[Partner]` labels leaked into outputs (since fixed)

**Pilot 2** (`run_A_20260601T172823Z`) — harder problems, random starter, seed 42
- Less echoing; influence scores lower (healthier discourse)
- **C anchored both tasks**; H1 flip: **no**
- Starters: C led 5/6 problems (random assignment)

**Pilot 3** (`run_B_20260601T173036Z`) — SQL block first, random starter, seed 42
- **S barely anchored both tasks** (thin margins: 0.392 vs 0.376 on coding)
- H1 flip: **no** — but **task order mattered**: first block (SQL) associated with S as session anchor
- Suggests **path dependence** (H0 variant), not expertise flip

**Pilot 4** (`run_A_20260601T175321Z`) — volunteer mode, domain tie-break, seed 42
- Both agents bid **LEAD on every problem** (no cost to volunteering)
- Domain expert selected 6/6 via **tie-break rule**, not behavior
- Influence: **S session anchor** despite C leading all coding problems
- Expertise framing affected **selection rule output**, not voluntary deferral

### Phase 1 conclusions (inform Phase 2 design)

1. **Expertise prompts alone** did not produce clean domain-specific anchoring
2. **First speaker / task order** confounded results — volunteer + tie-break still didn't fix it
3. **Both-always-LEAD** made volunteer phase uninformative — no penalty for leading
4. **Domain tie-break** artificially forced domain-aligned starters — blocked measuring anchor takeover
5. Need: **cost for leading**, **moderator selection from pitches**, **reward feedback**, Condition **C** (interleaved)

---

## Phase 2 — Pitch / moderator / rewards (current protocol)

**Status: one replicate complete (A, B, C @ seed 42).** See [known limitations](#known-limitations--planned-fixes) before treating as main results.

### Protocol summary

| Step | What happens |
|---|---|
| 1 | Problem shown; both agents see **cumulative scores** (public) |
| 2 | Both **pitch** privately (moderator has not seen partner's pitch) |
| 3 | **Moderator** selects leader from pitches |
| 4 | 6-turn discussion (leader opens, strict alternation) |
| 5 | **Grader**: PASS / FAIL on final solution |
| 6 | **Rewards** applied; scores updated in transcript |

### Conditions

| Condition | Problem order |
|---|---|
| **A** | 3 coding → 3 SQL (blocked) |
| **B** | 3 SQL → 3 coding (blocked) |
| **C** | coding, sql, coding, sql, … (interleaved) |

### Reward rules

| Outcome | Leader | Follower |
|---|---|---|
| Team **passes** | +1.5 (+1 + 0.5 bonus) | +1.0 |
| Team **fails** | −0.5 | 0 |

Both agents see each other's scores (competitive leaderboard dynamic).

### Phase 2 runs (seed 42)

| File | Condition | Order | Final scores | H1 flip | View |
|---|---|---|---|---|---|
| [`run_C_20260601T184655Z.json`](runs/run_C_20260601T184655Z.json) | C | coding ↔ sql interleaved | 7.5 / 7.5 | no | [HTML](runs/views/view_run_C_20260601T184655Z.html) |
| [`run_A_20260601T184908Z.json`](runs/run_A_20260601T184908Z.json) | A | 3 coding → 3 sql | 7.5 / 7.5 | **yes** | [HTML](runs/views/view_run_A_20260601T184908Z.html) |
| [`run_B_20260601T185101Z.json`](runs/run_B_20260601T185101Z.json) | B | 3 sql → 3 coding | 7.5 / 7.5 | no | [HTML](runs/views/view_run_B_20260601T185101Z.html) |

Analysis sidecars: `runs/run_*_analysis.json`

### What Phase 2 showed

**Manipulation / selection**
- Moderator picked domain expert on **18/18** problems (pitch selection, not tie-break rule)
- All **18/18** problems graded **PASS** — reward penalties never triggered
- Final scores tied **7.5 / 7.5** everywhere (3 leads × +1.5 + 3 follows × +1.0 per agent)

**Influence (H1)**
- **A**: flip detected — C dominant on coding block, S on SQL block
- **B**: no flip — S dominant even on coding block (session/path anchor)
- **C**: no flip — S dominant across both task types

**Pitch behavior**
- Both agents still pitch to **lead** on most problems (~4/6 off-domain pitches argued for lead)
- Off-domain deferral is prose-only (“I should not lead…”) — no structured `DEFER` bid like volunteer mode
- Over-bidding is rational: losing the pitch still yields +1.0 on team success; penalty only hits a failed **leader**

**Moderator “domain knowledge”**
- Moderator does **not** see agent system prompts (expertise framing)
- It **does** see: problem text (Python vs SQL), agent IDs (`code_expert` / `sql_expert`), and instructions to pick by “domain fit”
- Rationales like *“sql_expert has stronger domain fit for SQL aggregation”* come from names + problem type, not the manipulation

### Phase 2 research questions

1. **Caution** — do agents pitch deferral on off-domain problems when failure costs the leader −0.5?
2. **Cooperation vs sabotage** — after losing the pitch, does the follower help (team PASS) or undermine?
3. **Anchor takeover** — does one agent's pitch strengthen and win moderator selection across domains over time?

*(Phase 2 pilot could not answer (1)–(3) well: no failures, soft deferral, moderator IDs leak domain.)*

### Known limitations & planned fixes

| Issue | Why it matters | Planned fix |
|---|---|---|
| **LLM grader, 100% PASS** | Leader −0.5 never fires; rewards are decorative | Execution grading (HumanEval tests, SQL fixtures) |
| **Problems too easy** | Solo baseline ~6/6; teams always succeed | Calibrate to ~60–80% solo pass before main battery |
| **Moderator sees `code_expert` / `sql_expert`** | Selection ≈ domain-matching rule | Blind labels (`agent_alpha` / `agent_beta`) |
| **Pitch prompt always “bid to lead”** | Both compete to lead; deferral is optional prose | Structured `LEAD` / `DEFER` bids (like volunteer mode) |
| **No cost to over-bidding** | Safe to pitch lead off-domain and let moderator decide | Optional penalty for off-domain LEAD bids |

### How to run Phase 2

```bash
source .venv/bin/activate

# Recommended starting point
python scripts/run_experiment.py --condition C --seed 42

# Blocked conditions (task-order comparison)
python scripts/run_experiment.py --condition A --seed 42
python scripts/run_experiment.py --condition B --seed 42

# Analysis
python scripts/analyze_run.py runs/run_C_20260601T184655Z.json
python scripts/manipulation_check.py runs/run_C_20260601T184655Z.json
python scripts/view_run.py runs/run_C_20260601T184655Z.json --open
```

Phase 2 runs are saved as `runs/run_{A|B|C}_{timestamp}.json` with metadata fields:
- `starter_mode: "pitch"`
- `scoreboard` — cumulative scores and per-problem reward history
- `problem_starters` — pitches, moderator choice, PASS/FAIL, reward deltas

### Legacy modes (Phase 1 reproduction only)

```bash
python scripts/run_experiment.py --condition A --starter-mode volunteer --tiebreak random --seed 42
```

---

## Quick start (first time setup)

```bash
cd multi-agents
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — paste AZURE_OPENAI_API_KEY

python scripts/smoke_test.py
python scripts/run_baseline.py
```

## Azure Foundry setup

| Item | Value |
|---|---|
| Base URL | `https://armaan-foundry.services.ai.azure.com/openai/v1/` |
| Model deployment | `gpt-5.4-mini` |
| API key | Set in `.env` as `AZURE_OPENAI_API_KEY` |

## Project layout

```
src/
  config.py         # reads .env
  client.py         # Foundry Responses API wrapper
  agents.py         # prompts, moderator, pitch text
  experiment.py     # conversation loop + pitch/reward phases
  rewards.py        # scoring, grading, reward messages
  metrics.py        # anchor-absorber influence (I(A→B))
data/problems/
  coding.json       # HumanEval/43, 54, 65
  sql.json          # spider_hard_01–03
scripts/
  smoke_test.py
  run_baseline.py
  run_experiment.py
  analyze_run.py
  manipulation_check.py
  view_run.py       # chat-style HTML viewer for a run
runs/               # output JSON (gitignored)
  views/            # generated HTML from view_run.py
```

## Metrics reference

**`analyze_run.py`** — influence / anchoring
- `I(code_expert → sql_expert)` — TF-IDF cosine between adjacent turns
- Anchor vs absorber scores; task-boundary flip check (H1)

**`manipulation_check.py`** — framing / rewards
- Volunteer/pitch patterns, domain-aligned leadership
- Anchor takeover trajectory (early vs late problems)
- Reward PASS/FAIL history and final scores

## View a run (chat-style HTML)

Read a run as a visual timeline instead of raw JSON. Each problem card shows: **problem → pitches → leader selected → discussion → outcome**.

**Phase 2 (recommended starting point)**

| Condition | Chat viewer |
|---|---|
| C (interleaved) | [view_run_C_20260601T184655Z.html](runs/views/view_run_C_20260601T184655Z.html) |
| A (coding → sql) | [view_run_A_20260601T184908Z.html](runs/views/view_run_A_20260601T184908Z.html) |
| B (sql → coding) | [view_run_B_20260601T185101Z.html](runs/views/view_run_B_20260601T185101Z.html) |

**Phase 1 pilots**

| Run | Chat viewer |
|---|---|
| A, easy problems | [view_run_A_20260601T171051Z.html](runs/views/view_run_A_20260601T171051Z.html) |
| B, harder problems | [view_run_B_20260601T173036Z.html](runs/views/view_run_B_20260601T173036Z.html) |
| A, volunteer + domain tie-break | [view_run_A_20260601T175321Z.html](runs/views/view_run_A_20260601T175321Z.html) |

Generate or refresh viewers:

```bash
python scripts/view_run.py runs/run_C_20260601T184655Z.json --open
python scripts/view_run.py runs/run_A_20260601T184908Z.json runs/run_B_20260601T185101Z.json
python scripts/view_run.py 'runs/run_*.json'   # batch → runs/views/
```

## Troubleshooting

| Error | Likely cause |
|---|---|
| 401 Unauthorized | Wrong or missing API key in `.env` |
| 404 Not Found | Wrong base URL or model deployment name |
| 400 Model not supported | Deployment doesn't support Responses API |
| `manipulation_check.py: unrecognized arguments` | Pass one file path, or quote globs: `'runs/run_C_*.json'` for `analyze_run.py` only |
