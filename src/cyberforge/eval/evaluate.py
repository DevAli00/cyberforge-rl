"""Every player plays the same 1,000 new shifts; writes results.json and the plots (spec §7).

Usage: uv run python -m cyberforge.eval.evaluate [--shifts 1000]
Run it after training: it picks up models/w01_triage/*.zip and the learning curves.
"""

import argparse
import importlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cyberforge.agents.bandit import LearnedBandit
from cyberforge.agents.base import Policy
from cyberforge.agents.baselines import AlwaysPhishing, Random, SeverityFirst
from cyberforge.agents.oracle import Oracle
from cyberforge.agents.ppo import PPOPolicy
from cyberforge.agents.smart_analyst import SmartAnalyst
from cyberforge.eval.metrics import summarize
from cyberforge.eval.plots import (
    plot_actions_heatmap,
    plot_learning_curves,
    plot_stopped_before_impact,
)
from cyberforge.eval.runner import (
    TEST_SEED_START,
    EnvFactory,
    MaskedEnv,
    ShiftRecord,
    evaluation_seeds,
    play_shifts,
    real_env_factory,
)
from cyberforge.training.train_ppo import EXPERIMENT_DIR, MODELS_DIR

PPO_NAME = "maskable_ppo"
N_HAND_WRITTEN = 6


def hand_written_players(env: MaskedEnv, catalogue: Sequence[Any]) -> list[Policy]:
    """The six hand-written players of §6. The bandit and the analyst start fresh and learn
    online during the test shifts. The oracle reads `env.hidden_view()` of this same env."""
    return [
        Random(),
        SeverityFirst(catalogue),
        AlwaysPhishing(catalogue),
        LearnedBandit(n_actions=len(catalogue)),
        SmartAnalyst(catalogue),
        Oracle(env),
    ]


def evaluate(
    make_env: EnvFactory,
    catalogue: Sequence[Any],
    ppo_models: Sequence[Path] = (),
    n_shifts: int = 1_000,
) -> dict[str, Any]:
    """Results for every player on seeds 1_000_000 + i. PPO seeds are reported one by one and
    pooled under `maskable_ppo`."""
    seeds = evaluation_seeds(n_shifts)
    n_types = len(catalogue)
    players: dict[str, Any] = {}

    def run(env: MaskedEnv, policy: Policy) -> list[ShiftRecord]:
        records = play_shifts(env, policy, seeds)
        players[policy.name] = summarize(records, n_types)
        return records

    for index in range(N_HAND_WRITTEN):
        env = make_env()  # a fresh env per player; the oracle must read this one
        run(env, hand_written_players(env, catalogue)[index])

    pooled: list[ShiftRecord] = []
    for path in sorted(ppo_models):
        pooled += run(make_env(), PPOPolicy.load(path, name=f"{PPO_NAME}_{path.stem}"))
    if pooled:
        players[PPO_NAME] = summarize(pooled, n_types)

    return {
        "headline": "stopped_before_impact",
        "n_shifts": n_shifts,
        "seed_start": TEST_SEED_START,
        "alert_types": [rule.rule_id for rule in catalogue],
        "players": players,
    }


def write_outputs(results: dict[str, Any], experiment_dir: Path) -> None:
    """results.json (deterministic, sorted keys) and the three plots."""
    experiment_dir.mkdir(parents=True, exist_ok=True)
    (experiment_dir / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n"
    )
    players = results["players"]
    plot_stopped_before_impact(players, experiment_dir / "stopped_before_impact.png")

    curves = [
        json.loads(p.read_text()) for p in sorted(experiment_dir.glob("learning_curve_seed*.json"))
    ]
    if curves:
        baselines = {n: s["score"]["mean"] for n, s in players.items() if PPO_NAME not in n}
        plot_learning_curves(curves, baselines, experiment_dir / "learning_curve.png")

    hero = [n for n in (PPO_NAME, "severity_first") if n in players]
    plot_actions_heatmap(players, hero, results["alert_types"], experiment_dir / "hero_actions.png")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shifts", type=int, default=1_000)
    parser.add_argument("--models-dir", type=Path, default=MODELS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=EXPERIMENT_DIR)
    args = parser.parse_args(argv)

    make_env = real_env_factory()
    catalogue = importlib.import_module("cyberforge.envs.triage.catalogue").CATALOGUE
    models = sorted(args.models_dir.glob("*.zip"))
    results = evaluate(make_env, catalogue, models, args.shifts)
    write_outputs(results, args.experiment_dir)
    print(f"wrote {args.experiment_dir / 'results.json'}")


if __name__ == "__main__":
    main()
