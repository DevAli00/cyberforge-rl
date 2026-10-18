"""Plays players on many shifts and records what happened (spec §7)."""

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import gymnasium as gym
import numpy as np
from numpy.typing import NDArray

from cyberforge.agents.base import Policy
from cyberforge.agents.oracle import HiddenView

TEST_SEED_START = 1_000_000


class MaskedEnv(Protocol):
    """The §5 env as players see it: gymnasium's reset/step, `action_masks()`, `hidden_view()`."""

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[NDArray[np.float32], dict[str, Any]]: ...

    def step(
        self, action: int
    ) -> tuple[NDArray[np.float32], float, bool, bool, dict[str, Any]]: ...

    def action_masks(self) -> NDArray[np.bool_]: ...

    def hidden_view(self) -> HiddenView: ...


EnvFactory = Callable[[], MaskedEnv]


@dataclass
class ShiftRecord:
    """One shift played by one player. Counts come from the env's final `info` (§5)."""

    seed: int
    score: float
    attacks_total: int
    contained_early: int
    contained_stage3: int
    reached_impact: int
    false_alarms: int
    actions: list[int] = field(default_factory=list)

    @property
    def stopped_before_impact(self) -> int:
        """Headline number: attacks stopped at stage 1-3."""
        return self.contained_early + self.contained_stage3


def evaluation_seeds(n_shifts: int) -> list[int]:
    """The same new shifts for every player: seeds 1_000_000 + i."""
    return [TEST_SEED_START + i for i in range(n_shifts)]


def play_shift(env: MaskedEnv, policy: Policy, seed: int, rng: np.random.Generator) -> ShiftRecord:
    """Plays one shift. Players with an `update` method (bandit, smart analyst) learn as they go."""
    update = getattr(policy, "update", None)
    obs, info = env.reset(seed=seed)
    score = 0.0
    actions: list[int] = []
    terminated = truncated = False
    while not (terminated or truncated):
        action = policy.act(obs, env.action_masks(), rng)
        obs, reward, terminated, truncated, info = env.step(action)
        if update is not None:
            update(action, float(reward))
        score += float(reward)
        actions.append(action)
    return ShiftRecord(
        seed=seed,
        score=score,
        attacks_total=int(info["attacks_total"]),
        contained_early=int(info["contained_early"]),
        contained_stage3=int(info["contained_stage3"]),
        reached_impact=int(info["reached_impact"]),
        false_alarms=int(info["false_alarms"]),
        actions=actions,
    )


def play_shifts(
    env: MaskedEnv, policy: Policy, seeds: Sequence[int], player_seed: int = 0
) -> list[ShiftRecord]:
    """Plays `policy` on every seed, in order, with its own seeded generator."""
    rng = np.random.default_rng(player_seed)
    return [play_shift(env, policy, seed, rng) for seed in seeds]


def real_env_factory() -> EnvFactory:
    """Ali's `TriageEnv` with default settings. Fails clearly until it is merged."""
    try:
        module = importlib.import_module("cyberforge.envs.triage.env")
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "cyberforge.envs.triage.env.TriageEnv is not merged yet (spec §5)."
        ) from exc
    env_class: Callable[[], gym.Env[Any, Any]] = module.TriageEnv
    return env_class  # type: ignore[return-value]
