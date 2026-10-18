"""The SOC triage game (spec §4-5).

Real false alarms and attacks (generator.py). Attacks start on their turn but are not yet
opened, contained or advanced:
- TODO(#9): open, contain + reward (hand-written by Ali), advance, end-of-shift penalty.
"""

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from numpy.typing import NDArray

from cyberforge.envs.triage.catalogue import N_RULES
from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.generator import draw_attacks, draw_false_alarms, start_attack
from cyberforge.envs.triage.observation import (
    OBS_SIZE,
    action_mask,
    encode_observation,
    observation_high,
)
from cyberforge.envs.triage.types import (
    Alert,
    Attack,
    AttackStatus,
    HiddenView,
    InvalidActionError,
    ShiftStats,
)

Obs = NDArray[np.float32]


class TriageEnv(gym.Env[Obs, np.int64]):
    metadata: dict[str, Any] = {"render_modes": []}  # noqa: RUF012 (gymnasium API)

    def __init__(self, config: TriageConfig | None = None) -> None:
        super().__init__()
        self.config = config if config is not None else TriageConfig()
        self.action_space = spaces.Discrete(N_RULES)
        self.observation_space = spaces.Box(
            0.0, observation_high(self.config), (OBS_SIZE,), np.float32
        )
        self._turn = 0
        self._started = False
        self._done = False
        self._next_alert_id = 0
        self._inbox: tuple[Alert, ...] = ()
        self._arrived: tuple[Alert, ...] = ()
        self._attacks: tuple[Attack, ...] = ()
        self._stats = ShiftStats()

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[Obs, dict[str, Any]]:
        super().reset(seed=seed)
        self._turn = 0
        self._started = True
        self._done = False
        self._next_alert_id = 0
        self._inbox = ()
        self._attacks = draw_attacks(self.np_random, self.config)
        self._stats = ShiftStats(attacks_total=len(self._attacks))
        self._receive(self._arrivals(turn=0))
        return self._observation(), self._stats.as_info()

    def step(self, action: int | np.integer[Any]) -> tuple[Obs, float, bool, bool, dict[str, Any]]:
        if not self._started or self._done:
            raise RuntimeError("call reset() before step(): no shift is running")
        self._validate(action)

        # TODO(#9) spec §4.4 steps 1-3: open one alert of type `action`, contain + reward
        # (hand-written), advance unstopped attacks with generator.try_advance (-5 on reaching
        # stage 4); their alerts join this turn's arrivals.
        reward = 0.0

        next_turn = self._turn + 1
        self._receive(self._arrivals(turn=next_turn))  # §4.4 step 4
        self._turn = next_turn  # §4.4 step 5
        self._done = self._turn >= self.config.n_turns
        # TODO(#9): §4.4 step 5, -1 per attack still running below stage 4 when done.
        return self._observation(), reward, self._done, False, self._stats.as_info()

    def action_masks(self) -> NDArray[np.bool_]:
        return action_mask(self._inbox)

    def hidden_view(self) -> HiddenView:
        """The truth. Only the oracle may use it."""
        return HiddenView(turn=self._turn, attacks=self._attacks, inbox=self._inbox)

    def _validate(self, action: int | np.integer[Any]) -> None:
        if isinstance(action, bool) or not isinstance(action, int | np.integer):
            raise InvalidActionError(f"action must be an integer, got {action!r}")
        if not 0 <= action < N_RULES:
            raise InvalidActionError(f"action must be in [0, {N_RULES}), got {action}")
        if not self.action_masks()[action]:
            raise InvalidActionError(f"no alert of type {action} is waiting (mask is false)")

    def _receive(self, arrivals: tuple[Alert, ...]) -> None:
        self._arrived = arrivals
        self._inbox = (*self._inbox, *arrivals)

    def _arrivals(self, turn: int) -> tuple[Alert, ...]:
        """New false alarms for `turn`, then the stage-1 alert of each attack starting on it."""
        alarms = draw_false_alarms(self.np_random, self.config, turn, self._next_alert_id)
        self._next_alert_id += len(alarms)
        attacks: list[Attack] = []
        starts: list[Alert] = []
        for attack in self._attacks:
            if attack.status is AttackStatus.PENDING and attack.start_turn == turn:
                attack, alert = start_attack(self.np_random, attack, turn, self._next_alert_id)
                self._next_alert_id += 1
                starts.append(alert)
            attacks.append(attack)
        self._attacks = tuple(attacks)
        return (*alarms, *starts)

    def _observation(self) -> Obs:
        return encode_observation(self._inbox, self._arrived, self._turn, self.config)
