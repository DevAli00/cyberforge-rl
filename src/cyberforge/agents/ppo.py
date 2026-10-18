"""Wraps a trained MaskablePPO model as a §6 player."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sb3_contrib import MaskablePPO


class PPOPolicy:
    """Plays with the trained model, deterministic and with the action mask (spec §7)."""

    def __init__(self, model: MaskablePPO, name: str = "maskable_ppo") -> None:
        self.model = model
        self.name = name

    @classmethod
    def load(cls, path: str | Path, name: str = "maskable_ppo") -> "PPOPolicy":
        return cls(MaskablePPO.load(str(path), device="cpu"), name=name)

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        action, _ = self.model.predict(obs, action_masks=action_mask, deterministic=True)
        return int(action)
