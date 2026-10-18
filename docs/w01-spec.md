# W1 spec: SOC alert triage with attacks that progress

Status: **locked once PR #1 merges.** Any change after that goes through a PR approved by both tracks.

## 1. The game in one paragraph

A shift lasts 10 steps. Each step, about 10 new alerts arrive and the analyst (the agent) opens one. Hidden among the noise are 2–4 real attacks that move through a kill chain during the shift. Opening any alert that belongs to an attack contains the whole attack. Contain it early and you score; let it reach ransomware and you take a large penalty. Because opening a quiet early alert now prevents a disaster several steps later, this is a real sequential decision problem (credit assignment), not a bandit.

**The story:** severity-first triage loves `mass_file_rename` (severity 5), so it reliably catches ransomware *after* encryption has started. The agent should learn to hunt the quiet early stages.

All data is synthetic. Every number below is an assumption, stated as such in the README and the article.

## 2. Rule catalogue (`envs/triage/catalogue.py`)

`stage` is the kill-chain stage this rule reports when an attack fires it (– = never fired by attacks, pure noise). `noise_freq` is the share of noise alerts that come from this rule (sums to 1).

| rule_id | severity | source | stage | noise_freq |
|---|---|---|---|---|
| `phishing_link_clicked` | 3 | email | 1 initial access | 0.10 |
| `off_hours_login` | 1 | identity | 1 initial access | 0.14 |
| `new_admin_account` | 2 | identity | 2 foothold | 0.02 |
| `cloud_key_new_asn` | 2 | cloud | 2 foothold | 0.02 |
| `internal_port_scan` | 4 | ids | 3 spread | 0.12 |
| `mass_file_rename` | 5 | edr | 4 impact | 0.01 |
| `av_signature_hit` | 5 | edr | – | 0.16 |
| `encoded_powershell` | 4 | edr | – | 0.06 |
| `impossible_travel` | 3 | identity | – | 0.10 |
| `failed_login_burst` | 3 | identity | – | 0.12 |
| `dns_new_domain` | 2 | ids | – | 0.07 |
| `usb_device_inserted` | 1 | edr | – | 0.08 |

Rough precision per shift (attack alerts ÷ all alerts of that rule): phishing ≈ 14%, new admin ≈ 40%, port scan ≈ 15%, mass rename ≈ 60% but always too late. So there is no free answer: early rules are noisy, precise rules come late.

## 3. Generation (`envs/triage/generator.py`)

**Noise.** 9 noise alerts per step, rule drawn from `noise_freq`, machine criticality from `{1: 0.50, 2: 0.35, 3: 0.15}`.

**Attacks.** At `reset`:
- Number of attacks: uniform on {2, 3, 4}.
- Start step: uniform on {0, …, 5}.
- Target machine criticality: `{1: 0.20, 2: 0.30, 3: 0.50}` (attackers prefer important machines, so criticality is a weak signal).
- At its start step an attack enters stage 1 and fires one alert from a stage-1 rule (chosen uniformly).
- Each following step, an uncontained attack advances one stage with probability `p_advance = 0.6` and fires one alert from a rule of the new stage.
- Entering stage 4 = impact (ransomware). The attack stays uncontained-at-impact for scoring.

All randomness comes from the `np.random.Generator` the env owns, seeded in `reset(seed=...)`. No global RNG.

## 4. Step order (`envs/triage/env.py`)

At `reset`: generate attacks, then run arrivals for step 0, then return the first observation.

Each `step(action)`:
1. Open one alert of rule `action`: highest criticality first, then most recent arrival, then lowest `alert_id`.
2. If it belongs to an attack: contain it, remove that attack's other queued alerts, pay the containment reward (§5) based on the attack's **current** stage.
3. Uncontained attacks try to advance (§3). Any attack entering stage 4 pays the impact penalty.
4. New alerts arrive (noise + attack stage alerts).
5. `step += 1`. After 10 actions the shift ends: apply the end-of-shift penalty, `terminated = True`.

`terminated` (not `truncated`) at the end of the shift, because the horizon is part of the task and the step counter is in the observation.

## 5. Reward

| Event | Reward |
|---|---|
| Contain an attack at stage 1–2 | +1.0 |
| Contain at stage 3 | +0.5 |
| Open the alert of an attack already at stage 4 | +0.2 |
| An attack enters stage 4 while uncontained | −5.0 |
| False alarm | 0 |
| **End of shift: each attack still live (uncontained, below stage 4)** | **−1.0** |

The last row closes a loophole: without it, the agent learns to ignore attacks that start late because they can't reach stage 4 before the shift ends.

## 6. Observation and action (Gymnasium API)

| Item | Definition |
|---|---|
| Action space | `Discrete(12)`, index = row in the catalogue |
| `action_masks()` | `bool[12]`: true if at least one alert of that rule is in the queue |
| Observation space | `Box(0, inf, (49,), float32)` |
| Observation layout | `queued[rule, criticality]` counts (36) + `arrived_this_step[rule]` counts (12) + `step / 10` (1); counts scaled by 1/10 |
| `reset(seed, options)` | returns `(obs, info)` |
| `step(action)` | returns `(obs, reward, terminated, truncated, info)` |
| `info` | `attacks_total`, `contained_early` (stage 1–2), `contained_stage3`, `reached_impact`, `false_alarms` (cumulative this shift) |
| Hidden state | `env.hidden_view()` returns a read-only snapshot (attack stages + which queued alerts belong to which attack). **Only the oracle may use it.** |

The agent cannot see which alerts belong to attacks, so this is formally a POMDP. Treating the observation as the state is standard here.

Invalid action (mask false) raises `InvalidActionError`. Must pass `gymnasium.utils.env_checker.check_env`.

## 7. Policies (`agents/`)

```python
class Policy(Protocol):
    name: str

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int: ...
```

| Policy | Uses | Picks | Written by hand? |
|---|---|---|---|
| Random | mask | Uniform over valid rules | yes |
| Severity-first | catalogue severity + queue | Highest severity, then criticality | yes |
| Bandit (fixed) | per-rule mean reward estimated once by Monte Carlo (10k random shifts) | Greedy on that estimate | yes |
| Bandit (learned, ε-greedy) | its own running estimates | ε-greedy on per-rule mean reward, learns online | **yes: the update rule is the hand-written core of the week** |
| Smart analyst | domain knowledge only (stage rules, no hidden state) | Open stage-2 rules if present, else stage-1, else stage-3, else bandit | yes |
| Oracle | `hidden_view()` | Attack alert of the most advanced pre-impact attack; else any attack alert; else random | yes |
| **MaskablePPO** | obs + mask | Learned (`sb3-contrib`, `MlpPolicy`) | library |

## 8. Training and evaluation (`eval/`)

- **Training:** MaskablePPO, default hyperparameters first. 50,000 shifts (= 500k steps) per run, 5 seeds. Log episodic return every 1,000 shifts. If the curve hasn't flattened, go to 100k shifts.
- **Evaluation:** every policy on the same **1,000 held-out shifts**, seeds `1_000_000 + i`. PPO with `deterministic=True` and masks. Same config + seeds ⇒ byte-identical `results.json`.
- **Headline metric:** **attacks stopped before impact, per shift** (contained at stage 1–3), with 95% CI.
- Also report: attacks reaching impact per shift, mean return, false alarms opened, breakdown by containment stage.

## 9. Sanity checks before training PPO

| # | Check | Pass if |
|---|---|---|
| S1 | Oracle vs severity-first | Oracle stops ≥ 1 more attack per shift |
| S2 | Smart analyst vs fixed bandit | Smart analyst clearly better (non-overlapping CIs). If not, tune the game: stronger penalty, quieter early stages |
| S3 | No trivial answer | Every single-rule policy ("always open phishing if present, else random") is clearly below the smart analyst |

If a hand-written rule can't beat the bandit, PPO won't either. Fix the game first.

## 10. Plots

1. PPO learning curve (return vs shifts trained, mean ± std over 5 seeds) with baselines as horizontal lines.
2. Attacks stopped before impact per shift, per policy, with 95% CIs.
3. Outcome breakdown per policy: contained early / at stage 3 / reached impact / still live at shift end.
4. **Hero plot:** which rules each policy opens at each step (heatmap), PPO vs severity-first.
5. Stretch: impact penalty ablation (−2, −5, −10).

## 11. Dependencies

`gymnasium` (Track B, now), `stable-baselines3` + `sb3-contrib` + `torch` (Track A, when starting PPO).

## 12. Out of scope this week

LLMs (W3), real logs (W11), hyperparameter sweeps beyond the penalty ablation.
