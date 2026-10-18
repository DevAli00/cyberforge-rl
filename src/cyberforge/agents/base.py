"""Interface every player implements (spec §6)."""

from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class Policy(Protocol):
    name: str

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int: ...
