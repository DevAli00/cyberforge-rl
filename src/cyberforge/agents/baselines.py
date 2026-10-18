"""Hand-written baseline players of spec §6: Random, SeverityFirst and AlwaysPhishing."""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

N_IMPORTANCE = 3
PHISHING_RULE_ID = "phishing_link_clicked"


class Rule(Protocol):
    """The fields of a catalogue entry (`RuleSpec`) that the players read."""

    @property
    def rule_id(self) -> str: ...

    @property
    def severity(self) -> int: ...


def random_allowed(action_mask: NDArray[np.bool_], rng: np.random.Generator) -> int:
    """A uniformly random action among those allowed by the mask."""
    return int(rng.choice(np.flatnonzero(action_mask)))


class Random:
    """Any allowed alert type, uniformly at random. The floor."""

    name = "random"

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        return random_allowed(action_mask, rng)


class SeverityFirst:
    """Highest severity among allowed types, then the most important machine."""

    name = "severity_first"

    def __init__(self, catalogue: Sequence[Rule]) -> None:
        self.severities = [rule.severity for rule in catalogue]

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        n_types = len(self.severities)
        waiting = obs[: n_types * N_IMPORTANCE].reshape(n_types, N_IMPORTANCE)

        def priority(action: int) -> tuple[int, int]:
            top_importance = int(np.flatnonzero(waiting[action] > 0).max())
            return self.severities[action], top_importance

        allowed = [int(a) for a in np.flatnonzero(action_mask)]
        return max(allowed, key=priority)  # full ties: lowest index wins


class AlwaysPhishing:
    """Phishing if allowed, else any allowed type at random."""

    name = "always_phishing"

    def __init__(self, catalogue: Sequence[Rule]) -> None:
        self.phishing = next(
            i for i, rule in enumerate(catalogue) if rule.rule_id == PHISHING_RULE_ID
        )

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        if action_mask[self.phishing]:
            return self.phishing
        return random_allowed(action_mask, rng)
