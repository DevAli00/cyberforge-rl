"""Test doubles for the triage game, used until Ali's real env is merged.

`CATALOGUE` copies spec §4.3 and `FakeTriageEnv` has exactly the spaces of spec §5,
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

N_TYPES = 12
N_IMPORTANCE = 3
OBS_SIZE = N_TYPES * N_IMPORTANCE + N_TYPES + 1  # 49
TURNS_PER_SHIFT = 10
COUNT_SCALE = 0.1


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    severity: int
    source: str
    stage: int | None  # None = never raised by an attack (a dash in §4.3)
    noise_freq: float


# Provisional copy of spec §4.3, same order. Replace with Ali's
# cyberforge.envs.triage.catalogue.CATALOGUE once it is merged.
CATALOGUE: tuple[RuleSpec, ...] = (
    RuleSpec("phishing_link_clicked", 3, "email", 1, 0.10),
    RuleSpec("off_hours_login", 1, "identity", 1, 0.14),
    RuleSpec("new_admin_account", 2, "identity", 2, 0.02),
    RuleSpec("cloud_key_new_asn", 2, "cloud", 2, 0.02),
    RuleSpec("internal_port_scan", 4, "ids", 3, 0.12),
    RuleSpec("mass_file_rename", 5, "edr", 4, 0.01),
    RuleSpec("av_signature_hit", 5, "edr", None, 0.16),
    RuleSpec("encoded_powershell", 4, "edr", None, 0.06),
    RuleSpec("impossible_travel", 3, "identity", None, 0.10),
    RuleSpec("failed_login_burst", 3, "identity", None, 0.12),
    RuleSpec("dns_new_domain", 2, "ids", None, 0.07),
    RuleSpec("usb_device_inserted", 1, "edr", None, 0.08),
)


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
        self._attack_stages: list[int] = []

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[NDArray[np.float32], dict[str, Any]]:
        super().reset(seed=seed)
        self._turn = 0
        n_attacks = int(self.np_random.integers(2, 5))
        self._attack_stages = [int(s) for s in self.np_random.integers(1, 5, size=n_attacks)]
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

    def hidden_view(self) -> dict[str, Any]:
        """Fake truth snapshot (format not fixed by §5 yet). Oracle only."""
        return {
            "attacks": [
                {"attack_id": i, "stage": stage, "status": "running"}
                for i, stage in enumerate(self._attack_stages)
            ],
            "alert_owner": {},
        }

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
