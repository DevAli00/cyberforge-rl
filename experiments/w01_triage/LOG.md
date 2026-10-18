# W1 lab notebook: SOC triage game

Every experiment goes here, **failures as much as successes**: what we tried, the exact setup, the numbers, what broke, what we decided. Newest entries at the bottom. Re-run scripts live in `scripts/`.

**Entry format:** goal · setup (branch, commit, config, seeds, command) · result · verdict · decision / next step.

**Conventions:** "test shifts" = the same 1,000 new shifts for every player (seeds `1_000_000 + i`). "Stopped" = attacks stopped before ransomware, per shift (the headline). `±` = 95% confidence interval. About 3.05 attacks per shift on average.

---

## R1–R2 · 19:31–19:48 · Public data vs our numbers (research)

- **Goal:** check the catalogue and attack model against real public SOC data. Ali chose "match the data".
- **Setup:** two parallel research sessions; notes in `docs/research/w01-alert-noise.md` and `docs/research/w01-attack-progression.md`.
- **Result:**
  - **Backed:** ~90% noise (Microsoft 81–86%, Kaspersky ~90%), the stage order (MITRE ATT&CK, CISA AA24-109A), ransomware detected late.
  - **Contradicted:**
    - Stage-1 entry types: ransomware gets in mostly by brute force (26%) and stolen passwords (21%), with phishing ≤ 7% (Mandiant M-Trends 2025).
    - 5 severities, compared with the Sigma / Elastic / Microsoft defaults.
  - **No public data:** per-type `noise_freq`, 2–4 attacks per shift, the machine-importance splits.
  - **Conflict:** 1 turn ≈ 12 h matches attack speed, but gives the analyst only ~2 investigations a day, vs 10–20 in surveys.
- **Decision:**
  - stage 1 = `failed_login_burst` 0.48 / `off_hours_login` 0.39 / `phishing_link_clicked` 0.13 (new `attack_weight` field)
  - the 5 severity changes
  - 1 turn ≈ 12 h
  - merged in PR #25, commit `3b6363a`

## E1 · 20:14 · First real run: 6 hand-written players

- **Goal:** first end-to-end test of the real game; the §7 sanity checks.
- **Setup:**
  - branch `w01/turn-logic`, commit `db5d3ae`, default `TriageConfig` (fixed 9 false alarms/turn)
  - **`rules.py` = TEMPORARY Claude-written containment + reward** (Ali to rewrite by hand)
  - command: `uv run python -m cyberforge.eval.evaluate --shifts 1000`
- **Result:**

| Player | Stopped | Reached ransomware | Score / shift |
|---|---|---|---|
| oracle | 2.82 ± 0.05 | 0.18 | +1.86 |
| smart_analyst | 2.77 ± 0.05 | 0.24 | +1.41 |
| learned_bandit | 2.67 ± 0.05 | 0.33 | +0.85 |
| random | 1.02 ± 0.05 | 1.79 | −8.22 |
| always_phishing | 0.54 ± 0.04 | 2.22 | −10.88 |
| severity_first | 0.24 ± 0.03 | 2.49 | −12.10 |

- **Verdict:**
  - All 3 sanity checks pass: oracle vs severity-first +2.58; smart analyst > bandit on score but only just on stopped; always-phishing ≪ smart analyst.
  - **Severity-first is worse than random**: it opens `mass_file_rename` 30% of the time, after encryption.
  - **⚠️ Risk:** the bandit is close to the oracle (2.67 vs 2.82). Stage-2 types are rare false alarms (2% each), so even a bandit learns to open them. Little headroom for PPO on the headline.
- **Decision:** train PPO anyway (spec §7).

## E2 · 20:24 · PPO smoke test

- **Goal:** catch crashes and measure speed before the full run.
- **Setup:** `train_ppo --shifts 1000 --seeds 0`, outputs to scratch.
- **Result:** runs; average score −6.60 after 1,000 shifts; **~5 s per 1,000 shifts**.
- **Verdict:** OK. The spec estimated ~20 min for the full run; real ≈ 2–3 min.

## E3 · 20:25–20:27 · PPO full training + evaluation

- **Goal:** the W1 headline: does MaskablePPO beat the learned bandit?
- **Setup:**
  - commit `db5d3ae` (temporary rules), fixed 9 false alarms
  - MaskablePPO `MlpPolicy` with default settings, 3 seeds (0, 1, 2) × 30,000 shifts, run in parallel
  - commands: `uv run python -m cyberforge.training.train_ppo` then `uv run python -m cyberforge.eval.evaluate`
  - outputs: `results.json`, `learning_curve*.png/json`, `hero_actions.png`, `stopped_before_impact.png`; models in `models/w01_triage/` (git-ignored)
- **Result:**
  - Training took **2 min 03 s**.
  - Learning curve (training score) per seed, at 1k / 5k / 15k / 30k shifts:
    - seed 0: −6.60 / +1.66 / +1.89 / +2.04
    - seed 1: −6.56 / +1.74 / +1.90 / +1.99
    - seed 2: −6.66 / +1.64 / +1.83 / +1.80
  - Plateau by ~5,000 shifts.
  - Test shifts:

| Player | Stopped | Reached ransomware | Score / shift | Stopped at stage 1–2 / 3 |
|---|---|---|---|---|
| **maskable_ppo (3 seeds pooled)** | **2.89 ± 0.03** | **0.14** | **+2.07 ± 0.08** | 2.62 / 0.27 |
| ↳ seed 0 / 1 / 2 | 2.88 / 2.90 / 2.88 | | +2.02 / +2.13 / +2.05 | |
| oracle | 2.82 ± 0.05 | 0.18 | +1.86 | 2.73 / 0.09 |
| smart_analyst | 2.77 ± 0.05 | 0.24 | +1.41 | 2.43 / 0.34 |
| learned_bandit | 2.67 ± 0.05 | 0.33 | +0.85 | 2.29 / 0.38 |

- **Verdict:**
  - **PPO beats the bandit**: +0.22 stopped, ransomware cut from 0.33 to 0.14, score +2.07 vs +0.85. The CIs don't overlap, and all 3 seeds agree.
  - **Hero plot:** PPO opens entry types (`failed_login_burst`, `off_hours_login`) on turns 1–3, then switches to stage-2 types (`new_admin_account`, `cloud_key_new_asn`) on turns 4–9. That timing is something a bandit can't learn.
  - **PPO beats the "oracle"**, so the oracle is a greedy rule with perfect information, **not an upper bound**. Call it a "cheating heuristic" in the article, or improve it.
  - **Caveats:** temporary rules; possible leak (E4).
- **Decision:** check the leak before writing anything.

## E4 · 20:31 · Leak probe: does PPO count the 9 false alarms?

- **Hypothesis:** with exactly 9 false alarms per turn, "arrived this turn" counts summing above 9 reveal that an attack alert arrived. PPO might use this shortcut.
- **Setup:**
  - The **already-trained** E3 models, no retraining.
  - The same test shifts played twice: the normal game, and a game patched **in the script only** with Poisson(9) false alarms per turn.
  - Control group: bandit and smart analyst, which never read arrival counts.
  - Script: `scripts/leak_probe.py`, run from the repo root: `uv run python experiments/w01_triage/scripts/leak_probe.py 1000`.
- **Result:**
  - The shortcut is available on **65% of turns**.

| Player | Stopped (fixed 9) | (varying) | Change | Score change |
|---|---|---|---|---|
| PPO seeds 0 / 1 / 2 | 2.88 / 2.90 / 2.88 | 2.87 / 2.88 / 2.86 | −0.01 to −0.03 | −0.06 to −0.17 |
| learned_bandit (control) | 2.67 | 2.65 | −0.02 | −0.15 |
| smart_analyst (control) | 2.77 | 2.78 | +0.01 | +0.04 |
| oracle | 2.82 | 2.82 | 0.00 | −0.05 |

- **Verdict:**
  - **No evidence PPO uses the shortcut.** Its drop is the same size as the controls' and within the CIs, and it still beats the bandit in the varied game (2.87 vs 2.65).
  - **Limits:** one perturbation only; a PPO *trained* on a varying game could behave differently (that's E5).
- **Decision:** fix the leak anyway, for realism and so readers can't object. Ali asked to test all three shapes. New setting `noise_count` = fixed / binomial(18, 0.5) / Poisson(9) capped at 18 / uniform 6–12, default `fixed` (commit `13f8e02`, branch `w01/noise-count`).

## E5 · 20:34–20:39 · ❌ Training on the 3 varying-noise games (crashed)

- **Goal:** train PPO on each new game (3 seeds × 30,000 shifts) and compare against E3.
- **Setup:**
  - commit `13f8e02`, 9 jobs in parallel (3 games × 3 seeds)
  - script: `scripts/noise_experiment.py <out_dir>`
  - wall time 4 min 27 s
- **Result:**
  - **binomial ✅** and **uniform ✅**: models and learning curves saved.
  - **poisson ❌**: crashed with `InvalidActionError: no alert of type 9 is waiting (mask is false)`.
  - Because the script stops at the first failed job, **no evaluation ran for any game**.
- **Root cause (confirmed):** **the inbox can be completely empty.**
  - Poisson can draw 0 false alarms. If that happens on turn 1 and no attack starts on turn 1, all 12 buttons are greyed out, and MaskablePPO, with no allowed action left, picks one anyway.
  - Measured over 100,000 resets per game:

| Game | Shifts starting with an empty inbox |
|---|---|
| fixed | 0 |
| binomial | 0 |
| uniform | 0 |
| poisson | **10** (e.g. seed 9741: 0 false alarms, attacks start turns 4–6) |

  - With 30,000 training shifts per seed, that's ~3 hits per seed, so the crash was near-certain.
- **Lessons:**
  1. **The game rules never said what happens when there is nothing to open.** Fixed 9 false alarms hid this gap. Any setting allowing 0 arrivals (Poisson, or `noise_per_turn=0`) hits it. The game raising an error was correct: it refused an impossible move instead of silently doing something.
  2. **Experiment-script flaw:** one failed job aborted every evaluation. The script should record each job's failure and carry on with the others.
  3. The E4 probe didn't hit it: with ~1% per 1,000 shifts it was luck, not proof of safety.
- **Status:** open. Waiting on Ali's decision for the empty-inbox rule, then re-run E5.

## Fix · 20:50 · At least 1 false alarm per turn

- **Decision (Ali):** every noise shape draws at least 1 false alarm per turn, so there's always something to open. Other options considered: top up only when the inbox is empty (a hidden special rule), or a 13th "wait" action (changes the frozen §5 interface).
- **Setup:**
  - commit `2864ccb`; spec §4.1 + changelog updated
  - tests: at least 1 for every shape, even with an average of 1; the 3 crash seeds (9741, 10078, 21607) now start with a non-empty inbox
  - 340 tests pass
- **Also:** the experiment script now records a failed job and carries on (commit `9a1a845`).

## E6 · 20:55–21:00 · PPO on the 3 varying-noise games (re-run of E5)

- **Goal:** does PPO's lead over the bandit survive when the false-alarm count varies (no "more than 9" shortcut)? Which shape should become the default?
- **Setup:**
  - commit `9a1a845`; 3 shapes × 3 seeds × 30,000 shifts, 9 jobs in parallel, then all players on the test shifts of each game
  - command: `uv run python experiments/w01_triage/scripts/noise_experiment.py <out_dir>`
  - outputs: `e6_noise_count/` (per-game `results.json`, learning curves, plots, `summary.json`)
  - "fixed" column = E3 (commit `db5d3ae`; fixed games are unchanged by the at-least-1 rule)
- **Result:**
  - Wall time 5 min 06 s, **0 failed jobs**.

| Stopped before ransomware | fixed | binomial | poisson | uniform |
|---|---|---|---|---|
| maskable_ppo | **2.89** ± 0.03 | **2.86** ± 0.03 | **2.88** ± 0.03 | **2.88** ± 0.03 |
| oracle | 2.82 | 2.83 | 2.83 | 2.82 |
| smart_analyst | 2.77 | 2.77 | 2.79 | 2.79 |
| learned_bandit | 2.67 ± 0.05 | 2.72 ± 0.05 | 2.69 ± 0.05 | 2.62 ± 0.05 |
| random | 1.02 | 1.06 | 1.07 | 1.03 |
| severity_first | 0.24 | 0.25 | 0.25 | 0.25 |

| Score per shift | fixed | binomial | poisson | uniform |
|---|---|---|---|---|
| maskable_ppo | **+2.07** | **+1.92** | **+2.00** | **+2.00** |
| oracle | +1.86 | +1.88 | +1.83 | +1.80 |
| smart_analyst | +1.41 | +1.39 | +1.46 | +1.49 |
| learned_bandit | +0.85 | +1.09 | +0.91 | +0.55 |

| PPO minus bandit | fixed | binomial | poisson | uniform |
|---|---|---|---|---|
| stopped | +0.22 | +0.15 | +0.19 | +0.26 |
| reached ransomware | −0.19 | −0.12 | −0.16 | −0.22 |
| score | +1.22 | +0.83 | +1.09 | +1.44 |

  - PPO seeds agree in every game: stopped 2.85–2.90, score +1.82 to +2.13.
  - The learning curves plateau by ~5,000 shifts in every game.
  - **Same strategy everywhere:** turns 1–3 mostly `failed_login_burst` (31–35%); turns 4–9 mostly `new_admin_account` / `cloud_key_new_asn` (~32–35% each).
- **Verdict:**
  - ✅ **PPO's lead over the bandit holds in all 4 games**, with non-overlapping CIs on attacks stopped.
  - The lead is not caused by the fixed-count shortcut (consistent with E4).
  - PPO stays above the "oracle" heuristic everywhere (Q3).
  - The bandit is the least stable player (score +0.55 to +1.09 across games); PPO stays within +1.92 to +2.07.
- **Decision:** Ali picks the default shape (Q6).

---

## Open questions

| # | Question | Status |
|---|---|---|
| Q1 | What happens when the inbox is empty (no allowed action)? | ✅ Closed: at least 1 false alarm per turn (fix entry, E6) |
| Q2 | `rules.py` is temporary Claude-written code: Ali to rewrite by hand, then re-run E1 + E3 | Open |
| Q3 | Oracle is not an upper bound (PPO beats it): rename it in the article, or build a better one? | Open |
| Q4 | Little headroom between the bandit and the top on the headline (stage-2 types are giveaways) | Known risk, reported honestly |
| Q5 | Turn = 12 h matches attack speed, but analyst capacity is 5–10× too low | Stated in spec §4.2 |
| Q6 | Default `noise_count`: fixed, binomial, poisson or uniform? | **Open** (Ali) |
