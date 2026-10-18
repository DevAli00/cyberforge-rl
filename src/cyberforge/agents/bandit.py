"""Learned bandit of spec §6: running average of points per alert type, epsilon-greedy."""

import numpy as np
from numpy.typing import NDArray


class LearnedBandit:
    """Learns which alert type pays most right now. Ignores the observation on purpose."""

    name = "learned_bandit"

    def __init__(self, n_actions: int = 12, epsilon: float = 0.1) -> None:
        self.epsilon = epsilon
        self.values = np.zeros(n_actions, dtype=np.float64)  # average points per type
        self.counts = np.zeros(n_actions, dtype=np.float64)  # times each type was opened

    def update(self, action: int, reward: float) -> None:
        # Incremental mean: new_avg = old_avg + (reward - old_avg) / n,
        # so no need to keep every reward received.
        self.counts[action] += 1
        self.values[action] += (reward - self.values[action]) / self.counts[action]

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        allowed = np.flatnonzero(action_mask)
        if rng.random() < self.epsilon:
            return int(rng.choice(allowed))  # explore
        return int(allowed[np.argmax(self.values[allowed])])  # exploit; ties: lowest index
