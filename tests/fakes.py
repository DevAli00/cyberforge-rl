"""Test doubles for the triage game, used while Ali's env only has placeholder turn logic.

`CATALOGUE` is the real one. `FakeTriageEnv` has exactly the spaces of spec §5,
but the game logic is fake: observations and masks are random (yet consistent with
each other) and the reward is always 0. Do not import this from `src/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from numpy.typing import NDArray

# The real catalogue (PR #22); the env below stays fake.
from cyberforge.envs.triage.catalogue import CATALOGUE as CATALOGUE

N_TYPES = 12
N_IMPORTANCE = 3
OBS_SIZE = N_TYPES * N_IMPORTANCE + N_TYPES + 1  # 49
TURNS_PER_SHIFT = 10
COUNT_SCALE = 0.1


@dataclass(frozen=True)
class FakeAttack:
    """Same fields as Ali's `Attack` that the oracle reads."""

    attack_id: int
    stage: int
    status: str  # "active" or "contained", like AttackStatus


@dataclass(frozen=True)
class FakeAlert:
    """Same fields as Ali's `Alert`."""

    alert_id: int
    rule_index: int
    importance: int  # 1-3
    turn: int
    attack_id: int | None = None  # None = false alarm


@dataclass(frozen=True)
class FakeHiddenView:
    """Same shape as Ali's `HiddenView`."""

    turn: int
    attacks: tuple[FakeAttack, ...]
    inbox: tuple[FakeAlert, ...]


class FakeTriageEnv(gym.Env[NDArray[np.float32], np.int64]):
    """Random env with the §5 interface. All randomness comes from `self.np_random`."""

    metadata: dict[str, Any] = {"render_modes": []}  # noqa: RUF012

    def __init__(self) -> None:
        self.action_space = spaces.Discrete(N_TYPES)
        self.observation_space = spaces.Box(
            low=0.0, high=np.inf, shape=(OBS_SIZE,), dtype=np.float32
        )
        self._turn = 0
        self._mask = np.ones(N_TYPES, dtype=np.bool_)
        self._obs = np.zeros(OBS_SIZE, dtype=np.float32)
        self._info: dict[str, int] = {}
        self._attacks: tuple[FakeAttack, ...] = ()
        self._inbox: tuple[FakeAlert, ...] = ()

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[NDArray[np.float32], dict[str, Any]]:
        super().reset(seed=seed)
        self._turn = 0
        n_attacks = int(self.np_random.integers(2, 5))
        self._attacks = tuple(
            FakeAttack(i, int(stage), "active")
            for i, stage in enumerate(self.np_random.integers(1, 5, size=n_attacks))
        )
        self._info = {
            "attacks_total": n_attacks,
            "contained_early": 0,
            "contained_stage3": 0,
            "reached_impact": 0,
            "false_alarms": 0,
        }
        self._draw()
        return self._obs.copy(), dict(self._info)

    def step(
        self, action: np.int64 | int
    ) -> tuple[NDArray[np.float32], float, bool, bool, dict[str, Any]]:
        # No InvalidActionError here: check_env steps with unmasked random actions.
        self._turn += 1
        self._info["false_alarms"] += 1
        self._draw()
        terminated = self._turn >= TURNS_PER_SHIFT
        return self._obs.copy(), 0.0, terminated, False, dict(self._info)

    def action_masks(self) -> NDArray[np.bool_]:
        return self._mask.copy()

    def hidden_view(self) -> FakeHiddenView:
        """Fake truth snapshot with the shape of Ali's `HiddenView`. Oracle only."""
        return FakeHiddenView(turn=self._turn, attacks=self._attacks, inbox=self._inbox)

    def _draw(self) -> None:
        """Draw a random mask with at least one True and an observation matching it."""
        rng = self.np_random
        mask = rng.random(N_TYPES) < 0.6
        mask[rng.integers(N_TYPES)] = True

        waiting = rng.integers(0, 4, size=(N_TYPES, N_IMPORTANCE))
        waiting[~mask] = 0
        empty = mask & (waiting.sum(axis=1) == 0)
        waiting[empty, rng.integers(N_IMPORTANCE, size=int(empty.sum()))] = 1
        # Alerts that arrived this turn are still waiting, so never more than waiting.
        arrived = rng.integers(0, waiting.sum(axis=1) + 1)

        obs = np.empty(OBS_SIZE, dtype=np.float32)
        obs[: N_TYPES * N_IMPORTANCE] = waiting.reshape(-1) * COUNT_SCALE
        obs[N_TYPES * N_IMPORTANCE : -1] = arrived * COUNT_SCALE
        obs[-1] = self._turn / TURNS_PER_SHIFT
        self._mask = mask
        self._obs = obs
        # One alert per waiting count; each attack owns at most one of them.
        cells = [(t, imp) for t, imp in np.argwhere(waiting > 0) for _ in range(waiting[t, imp])]
        owners: list[int | None] = [None] * len(cells)
        for attack in self._attacks:
            if rng.random() < 0.7:
                owners[int(rng.integers(len(cells)))] = attack.attack_id
        self._inbox = tuple(
            FakeAlert(i, int(t), int(imp) + 1, self._turn, owner)
            for i, ((t, imp), owner) in enumerate(zip(cells, owners, strict=True))
        )
