"""Trains MaskablePPO on the triage game (spec §7): 3 seeds x 30,000 shifts, in parallel.

Usage: uv run python -m cyberforge.training.train_ppo [--shifts 30000] [--seeds 0 1 2]
Models go to models/w01_triage/ (git-ignored), learning curves to experiments/w01_triage/.
"""

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, cast

import gymnasium as gym
import numpy as np
import torch
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback

from cyberforge.eval.runner import EnvFactory, real_env_factory

TURNS_PER_SHIFT = 10
LOG_EVERY_SHIFTS = 1_000
MODELS_DIR = Path("models/w01_triage")
EXPERIMENT_DIR = Path("experiments/w01_triage")


class ShiftScoreLogger(BaseCallback):
    """Records the average shift score every `log_every` finished shifts."""

    def __init__(self, log_every: int = LOG_EVERY_SHIFTS) -> None:
        super().__init__()
        self.log_every = log_every
        self.curve: list[dict[str, float]] = []
        self._scores: list[float] = []
        self._running = 0.0

    def _on_step(self) -> bool:
        self._running += float(self.locals["rewards"][0])
        if bool(self.locals["dones"][0]):
            self._scores.append(self._running)
            self._running = 0.0
            if len(self._scores) % self.log_every == 0:
                recent = self._scores[-self.log_every :]
                self.curve.append(
                    {"shifts": len(self._scores), "mean_score": float(np.mean(recent))}
                )
        return True


def train(
    make_env: EnvFactory,
    seed: int,
    n_shifts: int,
    log_every: int = LOG_EVERY_SHIFTS,
    ppo_kwargs: dict[str, Any] | None = None,
) -> tuple[MaskablePPO, list[dict[str, float]]]:
    """Trains one MaskablePPO (MlpPolicy, default settings) and returns it with its curve."""
    env = cast(gym.Env[Any, Any], make_env())  # MaskablePPO reads env.action_masks() itself
    model = MaskablePPO("MlpPolicy", env, seed=seed, verbose=0, device="cpu", **(ppo_kwargs or {}))
    logger = ShiftScoreLogger(log_every)
    model.learn(total_timesteps=n_shifts * TURNS_PER_SHIFT, callback=logger)
    return model, logger.curve


def train_and_save(
    make_env: EnvFactory, seed: int, n_shifts: int, models_dir: Path, experiment_dir: Path
) -> Path:
    """Trains one seed, saves the model and its learning curve, returns the model path."""
    torch.set_num_threads(1)  # seeds run in parallel processes
    model, curve = train(make_env, seed, n_shifts)
    models_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / f"maskable_ppo_seed{seed}.zip"
    model.save(str(model_path))
    curve_path = experiment_dir / f"learning_curve_seed{seed}.json"
    curve_path.write_text(json.dumps(curve, indent=2, sort_keys=True) + "\n")
    return model_path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shifts", type=int, default=30_000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--models-dir", type=Path, default=MODELS_DIR)
    parser.add_argument("--experiment-dir", type=Path, default=EXPERIMENT_DIR)
    args = parser.parse_args(argv)

    make_env = real_env_factory()
    with ProcessPoolExecutor(max_workers=len(args.seeds)) as pool:
        futures = [
            pool.submit(
                train_and_save, make_env, seed, args.shifts, args.models_dir, args.experiment_dir
            )
            for seed in args.seeds
        ]
        for future in futures:
            print(f"saved {future.result()}")


if __name__ == "__main__":
    main()
