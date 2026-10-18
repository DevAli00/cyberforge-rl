# W1 spec: the SOC triage game

This is our map for W1. It is a **living document**: if we find something while building (a number that doesn't work, a loophole), we change it through a small PR and add a line to the [changelog](#11-changelog) at the bottom.

**Owners:** Ali builds the game (environment). Rayane builds the players (agents). We meet at the sync points in §9.

---

## 1. The game in plain words

A SOC analyst works a **shift**. During the shift, alerts keep arriving in the inbox. Most are false alarms. A few belong to **real attacks** that get worse over time. The analyst can only open **one alert per turn**, so they must choose well.

If the analyst opens any alert that belongs to an attack, **the whole attack is stopped**. Stop it early and you score points. Let it reach ransomware and you lose a lot of points.

The agent's job: learn which alerts are worth opening, and when.

**The story we want to tell:** "sort by severity" loves `mass_file_rename` (severity 5), so it catches ransomware *after* the files are already encrypted. A good analyst (or agent) hunts the quiet early signs instead.

All data is synthetic. Every number below is an assumption, and we say so in the README and the article.

## 2. Glossary

| Word | Meaning |
|---|---|
| **Shift** | One round of the game (one analyst work day). Starts, runs 10 turns, ends with a score. |
| **Turn (step)** | One move inside a shift. Each turn: the analyst opens one alert, attacks may advance, new alerts arrive. |
| **Alert** | One line in the SOC inbox, e.g. "phishing link clicked on PC-42". |
| **Alert type (rule)** | The kind of alert. There are 12. The agent picks a type; the game picks which alert of that type. |
| **Attack** | A hidden real attacker. Moves through 4 stages and creates one alert at each stage. |
| **Stage** | 1 gets in → 2 settles in → 3 spreads → 4 ransomware. |
| **Contain / stop** | Opening any alert of an attack stops the whole attack. |
| **Reward** | Points the agent gets after each turn. |
| **Episode** | RL word for one shift. |
| **Observation** | What the agent sees each turn: counts of waiting alerts, new arrivals, the turn number. Never which alerts are real. |
| **Mask** | Greys out impossible choices (alert types with nothing in the inbox). |
| **Seed** | Number that fixes the random dice. Same seed = same shift. |
| **Baseline** | A simple player we compare the agent against. |
| **Training** | The agent plays thousands of shifts and improves. |

## 3. One shift, step by step (example)

- **Turn 1:** 10 alerts arrive. Hidden inside: a phishing click from attack A (stage 1). The agent opens an AV hit → false alarm, 0 points. Attack A advances to stage 2 and creates a "new admin account" alert.
- **Turn 2:** the agent opens the "new admin account" alert → it's attack A → **attack A stopped, +1**.
- **Turns 3–6:** attack B starts on turn 3. The agent keeps opening false alarms. On turn 6, attack B reaches ransomware → **−5**.
- **Turn 10:** shift ends. Attack C started late and is still running → **−1**.
- **Score:** +1 − 5 − 1 = **−5**.

The −5 on turn 6 was caused by what the agent skipped on turns 3–4. Learning that link by itself is what makes this real RL, and what a simple bandit cannot do.

## 4. Game rules (Ali)

### 4.1 Shift shape

| Setting | Value |
|---|---|
| Turns per shift | 10 |
| False-alarm alerts arriving per turn | 9 (plus any attack alerts) |
| Alerts opened per turn | 1 |
| Unopened alerts | Stay in the inbox for later turns |

### 4.2 Attacks

| Setting | Value |
|---|---|
| Attacks per shift | Random: 2, 3 or 4 |
| Start turn | Random: turn 1 to 6 (step index 0–5) |
| One turn | ≈ **12 hours** of real time, so a 10-turn shift ≈ one 5-day SOC week. With `p_advance = 0.6` an attack needs 5 turns on average from stage 1 to 4 ≈ 2.5 days, inside the 17 h – 5 days measured from entry to ransomware (Sophos, Mandiant, Secureworks, Huntress). Known gap: one alert opened per turn = 2 deep investigations a day, below the 10–20 alerts per analyst per day in surveys |
| Speed | Each turn, an unstopped attack has a **60%** chance to move to the next stage (`p_advance = 0.6`) |
| Alerts | Exactly 1 alert each time an attack enters a stage, from an alert type of that stage, picked by its `attack_weight` |
| Target machine importance | 1: 20%, 2: 30%, 3: 50% (attackers prefer important machines) |
| After ransomware | The attack stays at stage 4. Opening its alert still gives +0.2 |

### 4.3 The 12 alert types (`envs/triage/catalogue.py`)

`noise_freq` = share of false alarms that are of this type (sums to 1). False alarms land on machines of importance 1: 50%, 2: 35%, 3: 15%.

`attack_weight` = chance that an attack entering that stage raises this type (sums to 1 per stage). Stage-1 weights follow how ransomware really gets in: brute force 26%, stolen credentials 21%, phishing ≤ 7% (Mandiant M-Trends 2025), rescaled to our three entry types. Severities follow the default Sigma / Elastic / Microsoft rule levels. Per-type `noise_freq` and the machine-importance splits have no public source: they stay **our assumption**.

| rule_id | severity | source | attack stage | noise_freq | attack_weight | In plain words |
|---|---|---|---|---|---|---|
| `phishing_link_clicked` | 4 | email | 1 | 0.10 | 0.13 | Very noisy early sign, rare way in for ransomware |
| `off_hours_login` | 1 | identity | 1 | 0.14 | 0.39 | Very noisy early sign (stolen password used) |
| `new_admin_account` | 2 | identity | 2 | 0.02 | 0.5 | Rare false alarm → good clue |
| `cloud_key_new_asn` | 3 | cloud | 2 | 0.02 | 0.5 | Rare false alarm → good clue |
| `internal_port_scan` | 2 | ids | 3 | 0.12 | 1.0 | Noisy and rated low, but means ransomware is close |
| `mass_file_rename` | 5 | edr | 4 | 0.01 | 1.0 | Almost always real, always too late; the only severity 5 |
| `av_signature_hit` | 4 | edr | – | 0.16 | 0 | Loud noise |
| `encoded_powershell` | 4 | edr | – | 0.06 | 0 | Noise |
| `impossible_travel` | 4 | identity | – | 0.10 | 0 | Noise (VPNs) |
| `failed_login_burst` | 3 | identity | 1 | 0.12 | 0.48 | Noisy, and the most common way ransomware gets in (brute force) |
| `dns_new_domain` | 2 | ids | – | 0.07 | 0 | Noise |
| `usb_device_inserted` | 1 | edr | – | 0.08 | 0 | Noise |

Design rule if we tune these: **early alert types stay noisy, late ones stay reliable.** Otherwise there is no tradeoff to learn.

### 4.4 What happens in one turn (exact order)

At `reset`: create the attacks, run the arrivals for turn 1, return the first observation.

On each `step(action)`:

1. **Open** one alert of type `action`: most important machine first, then most recent, then lowest `alert_id`.
2. If it belongs to an attack: **stop the attack**, remove that attack's other alerts from the inbox, give the reward for the attack's **current** stage.
3. Unstopped attacks **try to advance** (60%). Any attack reaching stage 4 gives −5.
4. **New alerts arrive** (9 false alarms + attack alerts from step 3 and attacks starting this turn).
5. Turn counter +1. After the 10th action the shift ends: −1 per attack still running below stage 4, `terminated = True`.

### 4.5 Points (reward)

| What happens | Points |
|---|---|
| Stop an attack at stage 1 or 2 | +1 |
| Stop it at stage 3 | +0.5 |
| Open it when it's already at ransomware (stage 4) | +0.2 |
| An attack reaches ransomware | **−5** |
| An attack is still running when the shift ends | −1 |
| Open a false alarm | 0 |

Why the −1: without it, the agent learns to ignore attacks that start late, because they can't reach ransomware before the shift ends.

## 5. Interface between game and players (frozen)

Rayane codes against this from minute one, using a fake env until the real one is merged. **Changing it needs both of us to agree.**

| Item | Definition |
|---|---|
| Class | `cyberforge.envs.triage.env.TriageEnv(gymnasium.Env)` |
| Settings | `TriageConfig`: frozen dataclass with the defaults from §4 (no YAML this week) |
| Catalogue | `cyberforge.envs.triage.catalogue.CATALOGUE`: tuple of 12 `RuleSpec(rule_id, severity, source, stage, noise_freq, attack_weight)` in the order of §4.3 |
| Action space | `Discrete(12)`: index = row in `CATALOGUE` |
| `action_masks()` | `np.ndarray[bool]` of shape (12,): true if at least one alert of that type is in the inbox |
| Observation space | `Box(0, high, (49,), float32)`, `high = observation.observation_high(config)`: the largest value each number can reach. Default config: 11.5 for waiting counts (11 arrival rounds × 9 false alarms + 4 attacks × 4 alerts = 115), 1.3 for arrivals (9 + 4), 1.0 for the turn |
| Observation layout | `[0:36]` waiting alerts per (type, importance 1–3), row-major by type · `[36:48]` alerts of each type that arrived this turn · `[48]` turn / 10 · all counts × 0.1 |
| `reset(seed=None, options=None)` | returns `(obs, info)` |
| `step(action)` | returns `(obs, reward, terminated, truncated, info)`; `truncated` is always `False` |
| `info` | `attacks_total`, `contained_early` (stage 1–2), `contained_stage3`, `reached_impact`, `false_alarms` (running totals for this shift) |
| `hidden_view()` | Read-only snapshot of the truth, a frozen `types.HiddenView(turn, attacks, inbox)`. Each `Attack`: `attack_id`, `start_turn`, `importance`, `stage` (0 = not started, 1–4), `status` (`pending` / `active` / `contained`). Each `Alert` in `inbox`: `alert_id`, `rule_index`, `importance`, `turn`, `attack_id` (`None` = false alarm). **Only the oracle may use it.** |
| Invalid action | Mask is false, out of range or not an integer → raise `InvalidActionError`; the game is unchanged |
| Must pass | `gymnasium.utils.env_checker.check_env`, with warnings as errors. `check_env` presses random actions and ignores the mask, so the test runs it on a test-only subclass that swaps a masked action for the first allowed one; the real game keeps raising |

Randomness: only from the env's own generator, seeded by `reset(seed=...)`. No global random.

The agent can't see which alerts are real, so this is formally a POMDP (partially observable). Treating the observation as the state is standard and fine here.

## 6. Players (Rayane)

```python
class Policy(Protocol):
    name: str

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int: ...
```

| Player | How it plays | Why it's here |
|---|---|---|
| Random | Any allowed type | Floor |
| Severity-first | Highest severity among allowed types, then most important machine | "A simplified SOC today" |
| Learned bandit | Running average points per alert type, ε-greedy. **Update rule written by hand.** | **The key opponent.** Only looks at points right now. If PPO doesn't beat it, the RL claim fails |
| Smart analyst | Stage-2 types if any, else stage 3, else stage 1, else bandit | Expert rule. Stage 3 before stage 1 because ransomware is one step away |
| Always-phishing | Phishing if any, else random | Checks there's no trivial answer |
| Oracle | Uses `hidden_view()`: opens an alert of the attack closest to ransomware | Upper bound |
| **MaskablePPO** | `sb3-contrib`, `MlpPolicy`, default settings first | The agent |

## 7. Training and testing

| Item | Value |
|---|---|
| Training | MaskablePPO, **3 seeds × 30,000 shifts** (300k steps each), in parallel, ~20 min on the M4. Log the average shift score every 1,000 shifts. |
| Testing | Every player plays the **same 1,000 new shifts** (seeds `1_000_000 + i`). PPO plays with `deterministic=True` and masks. |
| **Headline number** | **Attacks stopped before ransomware, per shift** (stopped at stage 1–3), with 95% CI |
| Also report | Attacks that reached ransomware per shift, average shift score, false alarms opened, breakdown by stage stopped |
| Output | `experiments/w01_triage/results.json` (deterministic, sorted keys) + plots. Models are git-ignored. |

### Sanity checks before training PPO (together)

Every hand-written player plays 1,000 shifts.

| Check | Passes if | If it fails |
|---|---|---|
| Oracle vs severity-first | Oracle stops ≥ 1 more attack per shift | Make early alert types less noisy |
| Smart analyst vs bandit | Smart analyst clearly better | Raise −5, or slow attacks (`p_advance` 0.6 → 0.5) |
| Always-phishing vs smart analyst | Clearly worse | Make phishing noisier |

Tune **once** (max 15 min). If it still fails, train anyway and write the honest result.

### Plots

1. PPO learning curve (score vs shifts played, mean ± spread over 3 seeds), baselines as flat lines.
2. Attacks stopped before ransomware, per player, with 95% CIs.
3. **Hero plot:** which alert types each player opens at each turn (heatmap), PPO vs severity-first.

## 8. Files and ownership

| Path | Owner |
|---|---|
| `src/cyberforge/envs/triage/types.py`, `catalogue.py`, `generator.py`, `env.py`, `config.py`, `observation.py`, `rules.py` | Ali |
| `src/cyberforge/agents/` (policies, bandit, smart analyst, oracle) | Rayane |
| `src/cyberforge/training/train_ppo.py` | Rayane |
| `src/cyberforge/eval/` (runner, metrics, plots) | Rayane |
| `tests/` | Whoever owns the code under test |
| `README.md`, game diagram | Ali |
| Article | Both: Ali the security parts, Rayane the RL parts |

Hand-written by humans (AI may write tests and boilerplate): **Ali** the containment + reward logic, **Rayane** the bandit update rule.

## 9. Today's plan (5 hours)

| Time | Ali (game) | Rayane (players) |
|---|---|---|
| 0:00–0:15 | **Together:** read this spec, merge it | |
| 0:15–0:40 | Skeleton: types, catalogue, `TriageEnv` with real spaces and placeholder logic, passes `check_env` | Read MaskablePPO docs, `uv add stable-baselines3 sb3-contrib torch`, fake env for tests |
| **0:40** | **Sync 1:** skeleton PR merged | |
| 0:40–1:30 | Generators: false alarms + attacks (tests first) | Random, severity-first, oracle, always-phishing (tests first, property test on masks) |
| 1:30–2:15 | Turn logic, containment + reward (by hand), masks, `info` | Learned bandit (by hand) + smart analyst, then PPO training script |
| **2:15** | **Sync 2:** real game merged | |
| 2:15–2:45 | **Together:** sanity checks, tune once if needed | |
| **2:45** | | **Launch PPO** (3 seeds, background) |
| 2:45–3:45 | README, game diagram, article "SOC problem" + "game" sections, *bonus: play a shift by hand in the terminal* | Test runner on 1,000 shifts, results.json, plots (baselines first, then PPO) |
| 3:45–4:30 | **Together:** read the results, agree on one sentence for the hero plot, write the article | |
| 4:30–5:00 | **Together:** review, merge, tag `w01`, publish | |

### If things go wrong

| Problem | Fallback |
|---|---|
| Game not merged by 2:15 | Rayane keeps going on the fake env; push sync 2 by up to 30 min; drop the bonus |
| PPO doesn't beat the bandit | Still an article: "when triage doesn't need RL, and what would change that (host context, next week)" |
| PPO is slow | 1 seed, 20,000 shifts, say so in the article |
| Late at 4:30 | Tag tonight, publish tomorrow. Never skip the tag |

### Working with Claude Code

- One session per person, each on their own branch (`w01/game`, `w01/agents`).
- Always: "write tests from spec §X first, don't implement yet", then "implement until the tests pass".
- Read every diff before opening a PR. The other person reviews within 5 minutes.

## 10. Not this week

Host names / correlating alerts on the same machine (W2), LLMs (W3), real logs (W11), YAML configs, hyperparameter sweeps.

## 11. Changelog

| When | Change | Why |
|---|---|---|
| W1 start | First version agreed by Ali and Rayane | – |
| W1 skeleton (#3) | Observation space max: `inf` → exact per-number max from the config | `check_env` warns on an infinite max; a real bound also documents what the agent can see |
| W1 skeleton (#3) | New file `observation.py` (inbox → 49 numbers, mask, max) | Small pure functions, tested alone; keeps `env.py` for the turn logic |
| After sync 1 | `hidden_view()` format fixed: frozen `HiddenView(turn, attacks, inbox)` | §5 left it open; the oracle (#23) now reads this shape |
| After sync 1 | `check_env` runs through a test-only mask adapter | It ignores the mask, so it would fail once real alerts leave some types empty; a lenient config option was considered and rejected so the real game can never silently accept a masked action |
| W1 research (#6) | Numbers checked against public data (notes: `docs/research/w01-alert-noise.md`, `docs/research/w01-attack-progression.md`). Backed: ~90% noise (Microsoft 81–86%, Kaspersky ~90%), stage order (MITRE ATT&CK, CISA AA24-109A), ransomware detected late (Mandiant: ransom note in 44–49% of cases) | Ali chose to match the data |
| W1 research (#6) | Stage 1 gets a third type: `failed_login_burst` (stage `–` → 1); new `attack_weight` field (§4.3, §5); stage-1 weights 0.48 / 0.39 / 0.13 | Ransomware gets in mostly by brute force and stolen passwords, rarely by phishing (Mandiant M-Trends 2025) |
| W1 research (#6) | Severities: phishing 3 → 4, cloud key 2 → 3, port scan 4 → 2, AV hit 5 → 4, impossible travel 3 → 4 | Default levels of Sigma, Elastic and Microsoft rules |
| W1 research (#6) | Defined one turn ≈ 12 hours (§4.2); `p_advance` stays 0.6 | Matches 17 h – 5 days from entry to ransomware; analyst-capacity gap stated openly |
| W1 agents (#23) | §6: players that learn while playing implement `LearningPolicy` = `Policy` + `update(action, reward)`; the runner calls it after every `step` | The `Policy` protocol had no way to receive points, which the learned bandit and the smart analyst need |
