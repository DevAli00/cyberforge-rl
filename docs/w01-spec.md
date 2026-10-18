# W1 spec: SOC alert triage environment

Status: **locked once this PR merges.** Any change after that goes through a PR that both tracks approve, because Track A codes against these interfaces in parallel.

## 1. Problem

A SOC analyst gets a queue of ~100 alerts per shift and can only investigate a few. The agent picks which alerts to investigate. Reward is the number of real threats (true positives) found.

The point of the week: **severity labels are miscalibrated** (loud rules are mostly noise, some quiet rules are often real), so a learning agent should beat "sort by severity" and approach an oracle.

All data is synthetic. TP rates and frequencies below are assumptions, stated as such in the README and article.

## 2. Rule catalogue (`envs/triage/catalogue.py`)

`p_tp` is the true-positive probability for an asset of criticality 2. `freq` is the probability that an alert comes from this rule (sums to 1). `cost` is analyst-minutes to investigate (used by the v2 budget).

| rule_id | severity | source | cost | p_tp | freq |
|---|---|---|---|---|---|
| `av_signature_hit` | 5 | edr | 5 | 0.02 | 0.15 |
| `internal_port_scan` | 4 | ids | 4 | 0.03 | 0.12 |
| `mass_file_rename` | 5 | edr | 5 | 0.45 | 0.02 |
| `new_admin_account` | 2 | identity | 6 | 0.35 | 0.03 |
| `cloud_key_new_asn` | 2 | cloud | 10 | 0.30 | 0.03 |
| `encoded_powershell` | 4 | edr | 5 | 0.15 | 0.06 |
| `impossible_travel` | 3 | identity | 6 | 0.04 | 0.10 |
| `failed_login_burst` | 3 | identity | 6 | 0.03 | 0.12 |
| `off_hours_login` | 1 | identity | 6 | 0.01 | 0.15 |
| `dns_new_domain` | 2 | ids | 4 | 0.12 | 0.07 |
| `phishing_link_clicked` | 3 | email | 3 | 0.15 | 0.08 |
| `usb_device_inserted` | 1 | edr | 5 | 0.02 | 0.07 |

Expected base rate ≈ 7.5% at criticality 2.

Back-of-envelope with budget = 10: random ≈ 0.75 TP/shift, severity-sort ≈ 0.7, oracle ≈ 3.1. That gap is the article. **Gap check at 2:30** confirms it empirically.

With the v2 minute budget, the ranking changes because of cost: `phishing_link_clicked` (0.15 / 3 min) beats `cloud_key_new_asn` (0.30 / 10 min) per minute, and near the end of the shift only cheap rules fit. That is what makes v2 a real MDP.

## 3. Generation (`envs/triage/generator.py`)

- Asset criticality ∈ {1, 2, 3} with probabilities {0.50, 0.35, 0.15}.
- `P(TP) = sigmoid(logit(p_tp[rule]) + criticality_effect * (criticality - 2))`, `criticality_effect = 0.5`.
- One shift = `n_alerts` alerts, rule drawn from `freq`, label drawn from `P(TP)`.
- All randomness comes from the `np.random.Generator` passed in. No global RNG, ever.

## 4. Types (`envs/triage/types.py`)

All frozen dataclasses (or pydantic models with `frozen=True`).

| Type | Fields |
|---|---|
| `Source` | `StrEnum`: `edr`, `ids`, `identity`, `cloud`, `email` |
| `RuleSpec` | `rule_id: str`, `severity: int` (1–5), `source: Source`, `cost: int`, `p_tp: float`, `freq: float` |
| `Alert` | `alert_id: int`, `rule_id: str`, `severity: int`, `source: Source`, `criticality: int`, `cost: int`, `is_true_positive: bool` |
| `AlertView` | Same as `Alert` **without** `is_true_positive`. This is all an agent ever sees. |
| `Observation` | `queue: tuple[AlertView, ...]` (uninvestigated alerts), `budget_remaining: int`, `step: int` |
| `StepInfo` | `alert_id: int`, `rule_id: str`, `is_true_positive: bool`, `cost: int` |
| `StepResult` | `observation: Observation`, `reward: float`, `terminated: bool`, `info: StepInfo` |
| `Transition` | `observation`, `action: str`, `reward: float`, `next_observation`, `terminated: bool` |

Helper: `valid_actions(obs) -> frozenset[str]` returns rule_ids that have at least one alert in the queue **and** whose cost fits `budget_remaining`.

## 5. Environment (`envs/triage/env.py`)

| Item | Contract |
|---|---|
| Construction | `TriageEnv(config: TriageConfig, catalogue: tuple[RuleSpec, ...])` |
| `reset(seed: int) -> Observation` | Generates a new shift from `np.random.default_rng(seed)`. |
| `step(action: str) -> StepResult` | `action` is a `rule_id`. The env investigates the uninvestigated alert of that rule with the **highest criticality, ties broken by lowest `alert_id`**. |
| Reward | `1.0` if TP else `0.0`. Variant (config): multiply by criticality. |
| Budget | `budget_unit="count"` (v1): each step costs 1. `budget_unit="minutes"` (v2): each step costs the alert's `cost`. |
| Invalid action | Not in `valid_actions(obs)` → raise `InvalidActionError`. Agents must only pick valid actions. |
| Termination | `valid_actions` is empty (budget spent, queue empty, or nothing affordable). |
| Hidden truth | `Alert.is_true_positive` is revealed only in `StepInfo` after investigation, and to evaluation code via `env.shift_alerts` (read-only tuple) for recall. |

The env is stateful by nature (it owns the current shift). Everything it returns is immutable.

## 6. Config (`envs/triage/config.py`, `configs/w01_triage.yaml`)

Pydantic `TriageConfig(frozen=True)`:

| Field | Default |
|---|---|
| `n_alerts` | 100 |
| `budget` | 10 (v1) / 60 (v2) |
| `budget_unit` | `"count"` or `"minutes"` |
| `criticality_effect` | 0.5 |
| `reward_by_criticality` | `false` |

## 7. Agents (`agents/`)

```python
class Agent(Protocol):
    name: str

    def act(self, observation: Observation, rng: np.random.Generator) -> str: ...
    def update(self, transition: Transition) -> None: ...
```

- Learning agents keep their estimates **across shifts** (one agent instance per run). Their internal tables are the only mutable state, and that is intentional.
- Non-learning agents implement `update` as a no-op.

| Agent | Receives at construction | Picks |
|---|---|---|
| `RandomAgent` | – | Uniform over `valid_actions` |
| `SeveritySortAgent` | – | Highest severity in the queue, then highest criticality |
| `OracleAgent` | catalogue (incl. `p_tp`) + `criticality_effect` | Highest expected TP of the alert that would actually be investigated (v2: per minute) |
| `EpsilonGreedyAgent` | `epsilon` | Per-rule mean reward estimates |
| `UCB1Agent` | `c` | Untried valid rules first, then mean + c·sqrt(ln t / n) |
| `QLearningAgent` | `alpha`, `epsilon`, `gamma=1.0`, bucket size | State = `budget_remaining` bucket, action = rule |

## 8. Runner, metrics, seeds (`eval/`)

- One run = one agent × one seed × `n_shifts` (default 500).
- Shift `i` of run seed `s` uses env seed derived from `np.random.SeedSequence([s, i])`. The agent gets one RNG per run from `SeedSequence([s, 1_000_000])`. Same config + seed ⇒ byte-identical `results.json`.
- Per-shift metrics: `tp_caught`, `tp_present`, `recall = tp_caught / tp_present` (NaN-safe when 0), `oracle_expected_tp`, `regret = oracle_expected_tp - tp_caught_expected`.
- Grid: 6 agents (+ hyper-param variants) × 5 seeds × 500 shifts. Output: `experiments/w01_triage/results.json` + `plots/`.

## 9. Plots

1. Learning curves: TP caught per shift (rolling mean ± std over seeds).
2. Cumulative regret vs oracle.
3. Final recall per agent, bars with 95% CIs.
4. **Hero plot:** learned per-rule value vs true `p_tp`, colored by severity.
5. (v2) Q-learning: preferred rule vs remaining minutes.

## 10. Out of scope this week

Gymnasium API (W2), neural networks (W2), real data (W11), LLMs (W3).
