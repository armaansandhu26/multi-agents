# Next steps (Phase 3 plan)

This is our working plan after reviewing Phases 1 and 2. Written in plain language: what we're doing, why, and what we expect to learn from each step.

---

## The big picture

**The question we're really asking:**

> When two AI agents collaborate, what decides who leads and who follows — the expertise they *claim* to have, who *speaks first*, or what *happened earlier* in the session?

Phases 1–2 were smoke tests. They proved the pipeline works, but they also revealed three core problems in the original design:

1. **Our measurement was broken.** The original "influence" metric was word-overlap between turns. It measured *talking about the same thing*, not *changing each other's mind*. Every Phase 1–2 result based on that metric should be treated as exploratory only.
2. **Our manipulation has no control group.** We tell one agent "you're the code expert" — but we never run a version *without* that framing. So we can't tell if the framing does anything.
3. **Our rewards did not fire in the pilots.** All 18/18 Phase 2 problems passed. The −0.5 leader penalty never triggered, so the old risk/reward dynamic was decorative.

One genuinely interesting thing *did* show up twice in pilots: **whoever anchors the first block of problems tends to stay the anchor for the whole session** (path dependence). This may be a more real and more interesting finding than our original hypothesis. Phase 3 is designed to test it head-to-head against expertise framing.

---

## Step 1 — Real grading + harder problems

**Status: DONE for Phase 3 prep.** Coding uses **HumanEval** (164 candidates via `scripts/import_humaneval.py`); SQL uses the **Spider dev set** (1034 candidates via `scripts/import_spider.py`). Both banks were baseline-calibrated with execution grading. The final balanced experiment batteries are **8 coding + 8 SQL** in the 40–70% solo pass band, with mean pass rates around **48% coding** and **50% SQL**. `scripts/verify_problems.py` passes on the local banks.

```bash
python scripts/import_humaneval.py
python scripts/import_spider.py
python scripts/run_baseline.py --task coding --tier candidate --attempts 5
python scripts/run_baseline.py --task sql --tier candidate --attempts 5
python scripts/select_calibrated_problems.py --balance
python scripts/verify_problems.py
python scripts/run_experiment.py --condition C --seed 42 --problem-tier calibrated --problems-per-task 3
```

**Pilot note (seed 45, A/B/C, 3 problems per task; before the −2/calibration-memory update):** the calibrated battery is now producing useful PASS/FAIL variation in team runs. Across 18 problems, the matched A/B/C batch produced 12 passes and 6 failures, so reward penalties are no longer decorative. See:
- `runs/run_A_20260627T123014Z.json`
- `runs/run_B_20260627T123333Z.json`
- `runs/run_C_20260627T123652Z.json`
- `runs/behavior_seed45.csv`
- `runs/views/behavior_seed45.html`

**Remaining:** run more calibrated Phase 3 seeds before treating these behavioral patterns as stable.

**What:** Replace the LLM grader with execution-based grading:
- Coding: run the team's final function against the official HumanEval test cases in a sandboxed subprocess.
- SQL: run the team's final query against a SQLite database built from Spider fixtures, compare results to the gold query's results.

Then expand the problem bank, re-run the solo baseline, and keep only problems where a solo agent passes **40–70% of the time**. The current battery is 8+8 because that is the balanced in-band set available from the completed calibration.

**Why:** In the pilots, a same-model LLM effectively graded its own work and everything passed. We need *real failures* — without them the reward penalty never applies, and questions about caution and sabotage are untestable.

**What we get out of it:** Ground-truth PASS/FAIL we can trust, and a problem set hard enough that leading is genuinely risky.

---

## Step 2 — A measurement of influence we can trust

**Status: IMPLEMENTED.** Solution provenance is the primary metric (`src/provenance.py`, integrated into `scripts/analyze_run.py`); stance tracking via LLM judge is in `scripts/stance_analysis.py`; human labeling + per-metric agreement reporting is in `scripts/label_anchors.py`. The old lexical metric is kept as an explicitly-labeled secondary signal (and its TF-IDF mislabel is fixed — it was plain TF). **Remaining: produce current calibrated runs, then hand-label ~10 transcripts and check `--agreement`.**

**What:** Replace word-overlap with measures of *whose ideas actually won*:
- **Solution provenance** (primary): how similar is the final graded solution to each agent's *first proposal*? (Embedding similarity, not word counts.) Whoever's initial idea survived is the anchor.
- **Stance tracking** (secondary): an LLM judge labels each turn as *concede / revise / critique / propose new*. The agent that concedes more is the absorber.

Then **validate it**: hand-label ~10 transcripts ourselves for who anchored, and check the metric agrees with human judgment. If it doesn't, it's not a metric.

**Why:** Word-overlap between adjacent turns is symmetric, dominated by shared vocabulary (SQL keywords, function names), and rewards echoing. It cannot distinguish "A influenced B" from "A and B discussed the same query."

**What we get out of it:** A dependent variable that actually means "anchoring." Until this exists, no run tells us anything.

---

## Step 3 — Break the expert = leader = first-speaker knot

**Status: PARTIAL.** The CLI already has `--starter-mode random`, but final-answer submission, execution grading, and rewards currently run only in `starter_mode == "pitch"`. It needs to become a first-class Phase 3 condition before it can test first-speaker effects.

**What:** Add a **random-leader condition**: the leader is assigned by coin flip, ignoring pitches and domains entirely.

**Why:** In Phase 2 the moderator picked the domain expert 18/18 times, and the leader always speaks first. So "the expert anchored" might just mean "the first speaker anchored." We currently cannot tell expertise apart from turn order.

**What we get out of it:** If anchoring follows the *randomly assigned leader* rather than the *domain expert*, then expertise framing does nothing and first-speaker position is what matters. This single condition can falsify our main hypothesis — that's exactly what a good experiment does.

---

## Step 4 — Add the missing control groups + blind everything

**Status: PARTIAL.** System-visible labels are now masked as `agent_alpha` / `agent_beta` in the pitch-selection path, reward/selection messages use masked labels, partner-background hints are removed, and agents are told not to reveal private expertise framing. Full Step 4 is still pending: no-framing/swapped-framing controls have not been added yet.

**What:** Three framing conditions:
- **Framed (current):** "You are the code/SQL expert."
- **No framing (control):** both agents are generalists, identical prompts.
- **Swapped framing:** the agent prompted as the SQL expert is presented to everyone as the code expert, and vice versa.

And blind all the labels: agents are `agent_alpha` / `agent_beta` to the moderator *and to each other*. The current harness has started this; the remaining work is to parameterize the framing conditions cleanly.

**Why:** Right now there's no counterfactual — we've never run the experiment without the manipulation, so we can't say it causes anything. In the original pilots, the names `code_expert` / `sql_expert` leaked the domain to the moderator, so its "domain fit" choices were partly name-matching. The current harness masks those labels, but the no-framing/swapped-framing counterfactuals are still needed.

**What we get out of it:** The ability to actually answer H1 vs H0. If framed and no-framing sessions look identical, claimed expertise does nothing. If swapped framing flips who anchors, the *claim* (not anything real) is driving behavior — which would be the headline result.

---

## Step 5 — Enough data to believe ourselves

**What:**
- 10–20 seeds per condition (not 1).
- 12–20 problems per session (not 6) — takeover (H2) is a slow trajectory and can't show up in 6 problems.
- Permutation tests on influence asymmetry instead of eyeballing two averages.
- Write the analysis plan down *before* running the main battery, so we don't fool ourselves picking the analysis after seeing the data.

**Why:** Every conclusion so far ("A flipped, B didn't") is a single anecdote at seed 42. The margins we've been interpreting (0.392 vs 0.376) are noise.

**What we get out of it:** Results with error bars. The model is cheap; the only cost is harness time.

---

## Step 6 — Make the bidding mean something

**Status: PARTIAL.** The current harness now uses structured `BID: LEAD/DEFER`, `CONFIDENCE`, `CLAIM`, and `APPROACH` pitch fields. Agents can explicitly defer, and they may make strategic public competence claims, including bluffing/overclaiming, while not revealing hidden prompts or private framing. Reward pressure is stronger: leader success +3.0, follower success +1.0, leader failure −2.0.

**Current caution-pressure update:** the harness now shows recent calibration history to each agent and to the moderator. If an agent recently led and failed, especially after a high-confidence bid, its next `LEAD` bid is expected to explain why the new problem is different. The moderator is instructed to treat recent high-confidence failures as evidence, not as an automatic ban, so bluffing and recovery attempts remain possible.

**Pilot note (seed 45, before the −2/calibration-memory update):** there were 36 total bids across the matched A/B/C batch: 31 `LEAD` and 5 `DEFER`. All 5 defers came from the less-aligned agent for that task (`code_expert` on SQL or `sql_expert` on coding). Deferral confidence was lower than usual (61-78%), but defers usually did **not** follow a same-agent leader failure. Only 1/5 came after a previous team failure, and 0/5 came after that same agent personally led and failed. The early pattern is therefore: agents defer when they are less task-aligned and less confident, not because recent failure has made them cautious.

**Related seed-45 summary:** aligned agents bid `LEAD` on 18/18 opportunities; less-aligned agents still bid `LEAD` on 13/18 opportunities. After an agent personally led a failed problem, its next bid was still `LEAD` 6/6 times, with average confidence around 95%. This suggests the current reward pressure encourages leadership persistence/bluffing more than post-failure caution.

**What remains:** Optional confidence-weighted staking/proper scoring rule where overconfidence costs extra. This should wait until the basic structured pitch protocol has produced a few calibrated pilot runs.

**Why:** In the pilots, pitching to lead was too cheap and failures never happened. The stronger reward gap creates pressure to seek leadership, while `DEFER` and confidence fields let us measure caution, calibration, and bluffing.

**What we get out of it:** Tests whether agents are calibrated about their own limits, whether they bluff under score pressure, and whether losing bidders cooperate or undermine.

---

## Order of work and dependencies

```
Step 1 (real grading + problem bank)   ← DONE (8+8 balanced calibrated battery)
Step 2 (trustworthy influence metric)  ← DONE (validation labeling pending)
Step 3 (random-leader condition)       ← PARTIAL (--starter-mode random exists; grading/reward path needs generalizing)
Step 4 (controls + blinding)           ← PARTIAL (labels/background hints masked; framing variants pending)
Step 5 (main battery, many seeds)      ← needs 1–4 done
Step 6 (structured pressure bidding)   ← PARTIAL (LEAD/DEFER + confidence + claims implemented; confidence-weighted staking optional later)
```

## What success looks like

At the end of Phase 3 we can answer, with real evidence:

1. **Does claimed expertise change who anchors?** (framed vs no-framing vs swapped)
2. **Or is it just who speaks first?** (moderator-selected vs random leader)
3. **Or is it history?** (first-block path dependence across orders A/B/C — our accidental Phase 1/2 finding, now tested properly)
4. **Do agents know their limits when failure costs them?** (staked bids, real failures)

Any clear answer to 1–3 — including "the framing does nothing" — is a real result.
