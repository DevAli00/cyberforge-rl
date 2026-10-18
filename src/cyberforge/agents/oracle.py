"""Oracle of spec §6: reads the hidden truth and goes after the attack closest to ransomware.

The format of `hidden_view()` is not fixed by §5 yet. This module defines a provisional one
(`HiddenView`), which the fake env in `tests/fakes.py` follows. Ali's env must return the same
shape, or this module changes when the real env lands.
"""

from typing import Protocol, TypedDict

import numpy as np
from numpy.typing import NDArray


class AttackView(TypedDict):
    attack_id: int
    stage: int  # 1-4
    stopped: bool
    waiting_alert_types: list[int]  # catalogue indices of this attack's alerts in the inbox


class HiddenView(TypedDict):
    attacks: list[AttackView]


class HasHiddenView(Protocol):
    def hidden_view(self) -> HiddenView: ...


class Oracle:
    """Opens an alert type of the running attack with the highest stage.

    Ties go to the lowest `attack_id`. With no visible attack alert, it opens a random
    allowed type. Note: the env opens the alert of that type on the most important machine,
    which may be a false alarm on another machine (spec §4.4), so this is a near upper bound.
    """

    name = "oracle"

    def __init__(self, env: HasHiddenView) -> None:
        self.env = env

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        targets = [
            (attack["stage"], -attack["attack_id"], alert_type)
            for attack in self.env.hidden_view()["attacks"]
            if not attack["stopped"]
            for alert_type in attack["waiting_alert_types"]
            if action_mask[alert_type]
        ]
        if targets:
            return int(max(targets)[2])
        return int(rng.choice(np.flatnonzero(action_mask)))
