"""Interface every player implements (spec §6)."""

from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class Policy(Protocol):
    name: str

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int: ...


class LearningPolicy(Policy, Protocol):
    """A player that learns during play: the runner calls `update` after every step.

    §6 gives `Policy` no way to receive points, which the learned bandit needs.
    """

    def update(self, action: int, reward: float) -> None: ...
