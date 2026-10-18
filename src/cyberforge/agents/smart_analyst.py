"""Smart analyst of spec §6: an expert rule on attack stages, with the bandit as fallback."""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from cyberforge.agents.bandit import LearnedBandit

# Stage 3 before stage 1: ransomware is only one step away.
STAGE_PRIORITY = (2, 3, 1)


class StagedRule(Protocol):
    """The field of a catalogue entry (`RuleSpec`) the analyst reads."""

    @property
    def stage(self) -> int | None: ...


class SmartAnalyst:
    """Stage-2 types if any, else stage 3, else stage 1, else the bandit.

    Within a stage, the bandit picks among the allowed types of that stage, and it keeps
    learning from every step.
    """

    name = "smart_analyst"

    def __init__(
        self, catalogue: Sequence[StagedRule], bandit: LearnedBandit | None = None
    ) -> None:
        self.stages = np.array([rule.stage or 0 for rule in catalogue])
        self.bandit = bandit if bandit is not None else LearnedBandit(n_actions=len(catalogue))

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        for stage in STAGE_PRIORITY:
            candidates = action_mask & (self.stages == stage)
            if candidates.any():
                return self.bandit.act(obs, candidates, rng)
        return self.bandit.act(obs, action_mask, rng)

    def update(self, action: int, reward: float) -> None:
        self.bandit.update(action, reward)
