"""The SOC triage game (spec §4-5).

Turn order exactly as §4.4. Random content comes from generator.py; containment and reward
from rules.py (hand-written by Ali).
"""

from dataclasses import replace
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from numpy.typing import NDArray

from cyberforge.envs.triage.catalogue import N_RULES
from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.generator import (
    draw_attacks,
    draw_false_alarms,
    shuffle_arrivals,
    start_attack,
    try_advance,
)
from cyberforge.envs.triage.observation import (
    OBS_SIZE,
    action_mask,
    encode_observation,
    observation_high,
)
from cyberforge.envs.triage.rules import (
    contain,
    containment_points,
    end_of_shift_points,
    impact_points,
    opened_alert,
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
        next_turn = self._turn + 1
        reward = self._open(int(action))  # §4.4 steps 1-2
        advanced, impact = self._advance(next_turn)  # §4.4 step 3
        self._receive(self._arrivals(next_turn, advanced))  # §4.4 step 4
        self._turn = next_turn  # §4.4 step 5
        self._done = self._turn >= self.config.n_turns
        reward += impact
        if self._done:
            reward += end_of_shift_points(self._attacks, self.config)
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

    def _open(self, action: int) -> float:
        """Open one alert of type `action`, then contain its attack if it has one."""
        opened = opened_alert(self._inbox, action)
        rest = tuple(alert for alert in self._inbox if alert.alert_id != opened.alert_id)
        attack_stage = next(
            (a.stage for a in self._attacks if a.attack_id == opened.attack_id), None
        )
        self._attacks, self._inbox = contain(opened, self._attacks, rest)
        if attack_stage is None:
            self._stats = replace(self._stats, false_alarms=self._stats.false_alarms + 1)
            return 0.0
        if attack_stage <= 2:
            self._stats = replace(self._stats, contained_early=self._stats.contained_early + 1)
        elif attack_stage == 3:
            self._stats = replace(self._stats, contained_stage3=self._stats.contained_stage3 + 1)
        return containment_points(attack_stage, self.config)

    def _advance(self, turn: int) -> tuple[tuple[Alert, ...], float]:
        """Every attack rolls to move up a stage; returns the new alerts and the impact points."""
        attacks: list[Attack] = []
        alerts: list[Alert] = []
        points = 0.0
        for attack in self._attacks:
            moved, alert = try_advance(
                self.np_random, attack, self.config, turn, self._next_alert_id
            )
            if alert is not None:
                self._next_alert_id += 1
                alerts.append(alert)
            if moved.reached_impact and not attack.reached_impact:
                self._stats = replace(self._stats, reached_impact=self._stats.reached_impact + 1)
            points += impact_points(attack, moved, self.config)
            attacks.append(moved)
        self._attacks = tuple(attacks)
        return tuple(alerts), points

    def _arrivals(self, turn: int, advanced: tuple[Alert, ...] = ()) -> tuple[Alert, ...]:
        """False alarms, alerts of attacks that advanced, and stage-1 alerts of attacks starting
        on `turn`, shuffled so the id tie-break favours no one."""
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
        return shuffle_arrivals(self.np_random, (*advanced, *alarms, *starts))

    def _observation(self) -> Obs:
        return encode_observation(self._inbox, self._arrived, self._turn, self.config)
