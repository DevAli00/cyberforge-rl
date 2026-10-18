# cyberforge-rl

Reinforcement-learning environments for **defensive** cybersecurity: alert triage, vulnerability detection, sandboxed vulnerability patching and incident response. Each environment comes with procedurally generated scenarios, verifiable rewards and reproducible experiments.

Built in public, one Sunday at a time. Each week ships a tagged release and a write-up.

## Status

| Week | Environment | Concept | Tag | Write-up |
|---|---|---|---|---|
| W1 | SOC alert triage | Bandits, MDPs, tabular Q-learning | — | — |

## Quickstart

```bash
uv sync
uv run pytest
```

## Development

| Task | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy` |
| Tests + coverage | `uv run pytest` |

CI runs all four on every push and pull request. `main` must stay green.

## Layout

```
src/cyberforge/
  envs/      environments (one subpackage per domain)
  agents/    policies: baselines, bandits, RL agents, LLM policies
  eval/      experiment runner, metrics, plots
configs/     one YAML per experiment, seeds included
experiments/ results and plots, one directory per week
tests/
```

## Safety scope

Defensive tasks only. Any environment that executes code runs it in network-isolated, resource-limited, throwaway sandboxes.

## License

[Apache-2.0](LICENSE)
