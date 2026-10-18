"""Oracle of spec §6: reads the hidden truth and goes after the attack closest to ransomware.

It reads Ali's `HiddenView` (`cyberforge.envs.triage.types`, PR #22): `attacks` and the
waiting `inbox`. The protocols below describe only the fields it uses, so it does not import
the game and also works with the fake env of the tests.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

ACTIVE = "active"  # AttackStatus.ACTIVE is a StrEnum, so it compares equal to this
IMPACT_STAGE = 4


class AttackView(Protocol):
    @property
    def attack_id(self) -> int: ...

    @property
    def stage(self) -> int: ...

    @property
    def status(self) -> str: ...


class AlertView(Protocol):
    @property
    def alert_id(self) -> int: ...

    @property
    def rule_index(self) -> int: ...

    @property
    def importance(self) -> int: ...

    @property
    def turn(self) -> int: ...

    @property
    def attack_id(self) -> int | None: ...


class HiddenView(Protocol):
    @property
    def attacks(self) -> Sequence[AttackView]: ...

    @property
    def inbox(self) -> Sequence[AlertView]: ...


class HasHiddenView(Protocol):
    def hidden_view(self) -> HiddenView: ...


def opened_alert(inbox: Sequence[AlertView], rule_index: int) -> AlertView:
    """The alert the game opens for this type (spec §4.4 step 1): most important machine,
    then most recent, then lowest alert_id."""
    of_type = [alert for alert in inbox if alert.rule_index == rule_index]
    return max(of_type, key=lambda a: (a.importance, a.turn, -a.alert_id))


class Oracle:
    """Picks the type whose opened alert stops the running attack closest to ransomware.

    It only counts a type if the alert the game would open is really the attack's alert, so a
    louder false alarm of the same type on a more important machine is avoided. Attacks already
    at ransomware come last (opening them is only +0.2). Ties: lowest attack_id, then lowest
    type. With no attack alert on top of any allowed type, a random allowed type.
    """

    name = "oracle"

    def __init__(self, env: HasHiddenView) -> None:
        self.env = env

    def act(
        self, obs: NDArray[np.float32], action_mask: NDArray[np.bool_], rng: np.random.Generator
    ) -> int:
        view = self.env.hidden_view()
        running = {a.attack_id: a.stage for a in view.attacks if a.status == ACTIVE}
        targets = []
        for rule_index in map(int, np.flatnonzero(action_mask)):
            owner = opened_alert(view.inbox, rule_index).attack_id
            if owner in running:
                stage = running[owner]
                priority = -1 if stage == IMPACT_STAGE else stage
                targets.append((priority, -owner, -rule_index))
        if targets:
            return -max(targets)[2]
        return int(rng.choice(np.flatnonzero(action_mask)))
