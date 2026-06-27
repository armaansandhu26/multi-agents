# Multi-agent anchoring experiment

Does claimed domain authority (via system prompt) determine which agent **anchors** during multi-agent collaboration?

Inspired by the **anchor–absorber** framework from:

> Parfenova, Denzler & Pfeffer (2025). *Emergent Convergence in Multi-Agent LLM Annotation.* BlackboxNLP 2025.  
> [PDF](https://aclanthology.org/2025.blackboxnlp-1.12.pdf)

> **Current status:** Phases 1–2 were infrastructure smoke tests; their results are not trustworthy (old lexical influence metric, no control conditions, rewards that never fired). **See [NEXT_STEPS.md](NEXT_STEPS.md) for the Phase 3 plan.** Steps 1–2 are implemented and calibrated: grading is now **execution-based** (HumanEval + Spider), problem banks verify offline, and balanced calibrated batteries exist (**8 coding + 8 SQL**, ~48–50% solo pass). The primary anchoring metric is now **solution provenance**. The current harness masks agent labels as `agent_alpha` / `agent_beta` in moderator/system-visible text and tells agents not to reveal private expertise framing. Next: run a small calibrated Phase 3 pilot, then implement the random-leader and framing controls.

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

## Phase 2 — Pitch / moderator / rewards pilot

**Status: one replicate complete (A, B, C @ seed 42).** See [known limitations](#known-limitations--planned-fixes) before treating as main results.

### Protocol summary

| Step | What happens |
|---|---|
| 1 | Problem shown; both agents see **cumulative scores** (public) |
| 2 | Both **pitch** privately (moderator has not seen partner's pitch) |
| 3 | **Moderator** selects leader from pitches |
| 4 | 6-turn discussion (leader opens, strict alternation) |
| 5 | **Leader submits final solution** (single fenced code block) |
| 6 | **Execution grading**: HumanEval tests / SQL fixture comparison → PASS / FAIL |
| 7 | **Rewards** applied; scores updated in transcript |

### Conditions

| Condition | Problem order |
|---|---|
| **A** | 3 coding → 3 SQL (blocked) |
| **B** | 3 SQL → 3 coding (blocked) |
| **C** | coding, sql, coding, sql, … (interleaved) |

### Phase 2 pilot reward rules (historical)

| Outcome | Leader | Follower |
|---|---|---|
| Team **passes** | +1.5 (+1 + 0.5 bonus) | +1.0 |
| Team **fails** | −0.5 | 0 |

Both agents see each other's scores (competitive leaderboard dynamic).

### Current calibrated harness changes

The current harness keeps the same pitch → moderator → discussion → final-answer flow, but the pitch and reward protocol is stronger:

| Field | Meaning |
|---|---|
| `BID: LEAD or DEFER` | Agents can explicitly ask to lead or decline leadership |
| `CONFIDENCE: 0-100` | Self-reported confidence for calibration/bluff analysis |
| `CLAIM:` | Public competence claim; agents may strategically overclaim or bluff |
| `APPROACH:` | Concrete solution plan and risks |

Current reward pressure:

| Outcome | Leader | Follower |
|---|---|---|
| Team **passes** | +3.0 | +1.0 |
| Team **fails** | −2.0 | 0 |

Only the leader can earn the large success bonus, but only the leader is penalized on failure.

The current harness also shows recent calibration history before each pitch: who led, whether the team passed, the leader's bid/confidence when available, and the score change. The moderator sees the same history with masked labels, and should make a recent high-confidence failed leader give a stronger current reason to lead again without banning recovery attempts.

### Current calibrated pilot note (seed 45, pre-caution update)

A matched A/B/C pilot was run with `--seed 45 --problem-tier calibrated --problems-per-task 3` before the leader-failure penalty changed from `-1.0` to `-2.0` and before recent-calibration context was added:

| Condition | Run file | Final scores |
|---|---|---|
| A | [`run_A_20260627T123014Z.json`](runs/run_A_20260627T123014Z.json) | code 3.0 / sql 11.0 |
| B | [`run_B_20260627T123333Z.json`](runs/run_B_20260627T123333Z.json) | code 4.0 / sql 10.0 |
| C | [`run_C_20260627T123652Z.json`](runs/run_C_20260627T123652Z.json) | code 11.0 / sql 3.0 |

Behavior artifacts:
- CSV: [`behavior_seed45.csv`](runs/behavior_seed45.csv)
- Dashboard: [`behavior_seed45.html`](runs/views/behavior_seed45.html)

Early bidding pattern:
- 36 total agent bids: 31 `LEAD`, 5 `DEFER`
- All 5 `DEFER` bids came from the less-aligned agent for that task
- Defers had lower confidence (61-78%), but usually did not follow failure
- After same-agent leader failure, the next bid was still `LEAD` 6/6 times, average confidence about 95%

Interpretation for now: this pilot shows leadership pressure and strategic overclaiming/bluffing, but little evidence yet of post-failure caution. Treat this as an early pattern, not a final result.

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
- In the original Phase 2 pilot, both agents still pitched to **lead** on most problems (~4/6 off-domain pitches argued for lead)
- Deferral was prose-only (“I should not lead…”) — no structured `DEFER` bid like volunteer mode
- The current harness fixes this with structured `BID: LEAD or DEFER`, `CONFIDENCE`, and `CLAIM` lines, while allowing strategic public competence claims/bluffing

**Moderator “domain knowledge”**
- Moderator does **not** see agent system prompts (expertise framing)
- In the original Phase 2 pilot it **did** see: problem text (Python vs SQL), agent IDs (`code_expert` / `sql_expert`), and instructions to pick by “domain fit”
- Current harness masks system-visible labels as `agent_alpha` / `agent_beta` and removes partner-background hints from agent prompts; old pilot rationales like *“sql_expert has stronger domain fit for SQL aggregation”* came from names + problem type, not the manipulation

### Phase 2 research questions

1. **Caution** — do agents pitch deferral on high-risk or less-aligned problems when failure costs the leader −2.0?
2. **Cooperation vs sabotage** — after losing the pitch, does the follower help (team PASS) or undermine?
3. **Anchor takeover** — does one agent's pitch strengthen and win moderator selection across domains over time?

*(Phase 2 pilot could not answer (1)–(3) well: no failures, soft deferral, moderator IDs leak domain.)*

### Known limitations & planned fixes

| Issue | Why it matters | Status |
|---|---|---|
| **LLM grader, 100% PASS** | Leader −0.5 never fires; rewards are decorative | **FIXED** — execution grading (`src/execution_grading.py`) |
| **Problems too easy** | Solo baseline ~6/6; teams always succeed | **FIXED for Phase 3 prep** — banks expanded to 164 HumanEval + 1034 Spider; calibrated batteries are 8+8 in the 40–70% solo pass band |
| **Moderator sees `code_expert` / `sql_expert`** | Selection ≈ domain-matching rule | **PARTIAL FIX** — system-visible labels now use `agent_alpha` / `agent_beta`, partner-background hints are removed, and agents are told not to reveal private framing; full no-framing/swapped-framing controls still pending |
| **Pitch prompt always “bid to lead”** | Both compete to lead; deferral is optional prose | **FIXED for current harness** — structured `BID: LEAD/DEFER`, confidence, public claim, and approach |
| **Weak pressure to lead** | +0.5 leadership bonus was mild; following was comfortable | **UPDATED** — leader success +3.0, follower success +1.0, leader failure −2.0 plus recent-calibration context |
| **No way to measure bluffing** | Claims were unstructured prose | **PARTIAL FIX** — public `CLAIM` line is stored in `pitch_bids`; post-run bluff/leak analysis still pending |
| **Lexical influence metric** | Measures topical overlap/echoing, not influence | **FIXED** — provenance is primary (`src/provenance.py`); lexical kept as labeled legacy signal |

### How to run the current calibrated harness

```bash
source .venv/bin/activate

# 0. First-time/rebuild only: import problem banks (both tag tier=candidate)
python scripts/import_humaneval.py
python scripts/import_spider.py

# 1. Verify banks offline
python scripts/verify_problems.py

# 2. Reproduce calibration if needed (already done in this workspace)
python scripts/run_baseline.py --task coding --tier candidate --attempts 5
python scripts/run_baseline.py --task sql --tier candidate --attempts 5
python scripts/run_baseline.py --report-only
python scripts/select_calibrated_problems.py --balance

# 3. Run a calibrated pilot (same seed = same sampled problems across A/B/C)
python scripts/run_experiment.py --condition C --seed 42 --problem-tier calibrated --problems-per-task 3
python scripts/run_experiment.py --condition A --seed 42 --problem-tier calibrated --problems-per-task 3
python scripts/run_experiment.py --condition B --seed 42 --problem-tier calibrated --problems-per-task 3

# 4. Analysis (provenance is the primary anchoring measure)
python scripts/analyze_run.py runs/run_C_<timestamp>.json
python scripts/stance_analysis.py runs/run_C_<timestamp>.json   # LLM stance labels
python scripts/manipulation_check.py runs/run_C_<timestamp>.json
python scripts/behavior_analysis.py runs/run_C_<timestamp>.json --csv runs/behavior_rows.csv
python scripts/plot_behavior.py runs/run_C_<timestamp>.json --output runs/views/behavior_<timestamp>.html
python scripts/view_run.py runs/run_C_<timestamp>.json --open

# 5. Validate metrics against your own judgment
python scripts/label_anchors.py runs/run_C_<timestamp>.json              # label
python scripts/label_anchors.py runs/run_C_<timestamp>.json --agreement  # compare
```

Current harness runs are saved as `runs/run_{A|B|C}_{timestamp}.json` with metadata fields:
- `starter_mode: "pitch"`
- `scoreboard` — cumulative scores and per-problem reward history
- `problem_starters` — pitches, moderator choice, PASS/FAIL, reward deltas
- `problem_tier: "calibrated"` — when using the balanced Phase 3 battery

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
  config.py             # reads .env
  client.py             # Foundry Responses API wrapper
  agents.py             # prompts, moderator, pitch + final-answer text
  experiment.py         # conversation loop + pitch/final-answer/reward phases
  rewards.py            # scoring + reward messages
  execution_grading.py  # sandboxed HumanEval tests + SQL fixture comparison
  provenance.py         # PRIMARY metric: final solution vs first proposals
  metrics.py            # LEGACY lexical influence (secondary signal only)
data/problems/
  coding.json           # HumanEval (164 candidates; built by import_humaneval.py)
  coding_legacy.json    # backup of pre-import 33-problem bank
  coding_calibrated.json # 8-problem in-band battery after baseline (generated)
  sql.json              # Spider dev set (1034 candidates; built by import_spider.py)
  sql_legacy.json       # backup of hand-written bank (pre-Spider)
  sql_calibrated.json   # 8-problem in-band battery after baseline (generated)
  sql_fixtures.json     # legacy in-memory fixtures (sql_legacy only)
scripts/
  smoke_test.py
  verify_problems.py    # offline bank verification
  import_humaneval.py   # import HumanEval + build data/problems/coding.json
  import_spider.py      # download Spider + build data/problems/sql.json
  select_calibrated_problems.py  # pick 40-70% band; --balance matches battery sizes
  build_sql_bank.py     # legacy hand-written SQL bank builder
  run_baseline.py       # solo difficulty calibration (execution-graded)
  run_experiment.py
  analyze_run.py        # provenance + legacy influence
  behavior_analysis.py  # bid/confidence/claim/pass-fail behavior analysis
  plot_behavior.py      # HTML/SVG dashboard for bidding/confidence behavior
  stance_analysis.py    # LLM judge: PROPOSE/CRITIQUE/CONCEDE/... per turn
  label_anchors.py      # human labeling + metric agreement report
  manipulation_check.py
  view_run.py           # chat-style HTML viewer for a run
runs/                   # output JSON (gitignored)
  views/                # generated HTML from view_run.py
```

## Metrics reference

**`analyze_run.py`** — anchoring
- **Solution provenance (PRIMARY)**: similarity of the final graded solution to each agent's first proposal (TF-IDF cosine with real IDF + token-sequence ratio). Per-problem winner, per-task anchor, flip check (H1). Requires current-harness runs with final-answer turns.
- **Legacy lexical influence (secondary)**: `I(A → B)` term-frequency cosine between adjacent turns. Measures topical overlap/echoing — do not interpret as influence on its own.

**`stance_analysis.py`** — stance dynamics (LLM judge)
- Labels each turn PROPOSE / REVISE_OWN / CRITIQUE / CONCEDE / SUPPORT / RESTATE
- Concession rate + assertiveness per agent per task; stance anchor

**`label_anchors.py`** — metric validation
- Interactive human labeling of who anchored each problem
- `--agreement`: per-metric agreement vs human labels (provenance, stance, legacy)

**`manipulation_check.py`** — framing / rewards
- Volunteer/pitch patterns, domain-aligned leadership
- Anchor takeover trajectory (early vs late problems)
- Reward PASS/FAIL history and final scores

**`behavior_analysis.py`** — bidding / confidence / pressure
- Per-agent rows for `BID`, `CONFIDENCE`, public `CLAIM`, selection, PASS/FAIL, score pressure, and early/late phase
- Summaries for confidence calibration, less-aligned LEAD bids, post-failure caution, and behind/ahead score pressure
- Optional `--csv` export for plotting or statistical analysis

**`plot_behavior.py`** — visual behavior dashboard
- Dependency-free HTML/SVG plots for confidence timeline, selected-leader pass rate by confidence bin, and LEAD rate under pressure
- Generates browser-viewable files under `runs/views/`

## View a run (chat-style HTML)

Read a run as a visual timeline instead of raw JSON. Each problem card shows: **problem → pitches → leader selected → discussion → outcome**.

**Phase 2 pilot viewers**

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
