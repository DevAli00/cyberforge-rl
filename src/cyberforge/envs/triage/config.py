"""Game settings (spec §4). Frozen, defaults are the agreed W1 values."""

import math
from dataclasses import dataclass
from enum import StrEnum

from cyberforge.envs.triage.types import N_IMPORTANCE

ImportanceProbs = tuple[float, float, float]  # chance of importance 1, 2, 3

UNIFORM_NOISE_SPREAD = 3  # uniform: noise_per_turn - 3 to noise_per_turn + 3


class NoiseCount(StrEnum):
    """How many false alarms arrive per turn; all average `noise_per_turn`."""

    FIXED = "fixed"  # always exactly noise_per_turn
    BINOMIAL = "binomial"  # Binomial(2 x average, 0.5): 0 to 2 x average
    POISSON = "poisson"  # Poisson(average), capped at 2 x average
    UNIFORM = "uniform"  # every count in average +/- UNIFORM_NOISE_SPREAD equally likely


@dataclass(frozen=True, slots=True)
class TriageConfig:
    # §4.1 shift shape
    n_turns: int = 10
    noise_per_turn: int = 9  # average number of false alarms per turn
    noise_count: NoiseCount = NoiseCount.POISSON  # Ali's choice after E6
    # §4.2 attacks
    attack_count_choices: tuple[int, ...] = (2, 3, 4)
    max_start_turn: int = 5  # step index, inclusive (turn 1 to 6)
    p_advance: float = 0.6
    attack_importance_probs: ImportanceProbs = (0.2, 0.3, 0.5)
    # §4.3 false alarms
    noise_importance_probs: ImportanceProbs = (0.5, 0.35, 0.15)
    # §4.5 points
    reward_contain_early: float = 1.0  # stopped at stage 1-2
    reward_contain_stage3: float = 0.5
    reward_open_impact: float = 0.2  # opened after it reached ransomware
    penalty_impact: float = -5.0  # an attack reaches ransomware
    penalty_running_at_end: float = -1.0  # per attack still running when the shift ends
    # §5 observation
    count_scale: float = 0.1

    def __post_init__(self) -> None:
        self._check_noise_count()
        self._check_shift()
        self._check_attacks()
        self._check_probs("attack_importance_probs", self.attack_importance_probs)
        self._check_probs("noise_importance_probs", self.noise_importance_probs)
        self._check_points()

    @property
    def max_noise_per_turn(self) -> int:
        """The most false alarms that can arrive in one turn."""
        if self.noise_count is NoiseCount.FIXED:
            return self.noise_per_turn
        if self.noise_count is NoiseCount.UNIFORM:
            return self.noise_per_turn + UNIFORM_NOISE_SPREAD
        return 2 * self.noise_per_turn

    def _check_noise_count(self) -> None:
        try:
            object.__setattr__(self, "noise_count", NoiseCount(self.noise_count))
        except ValueError:
            names = ", ".join(NoiseCount)
            _require(False, f"noise_count must be one of {names}, got {self.noise_count!r}")
        if self.noise_count is NoiseCount.UNIFORM:
            _require(
                self.noise_per_turn >= UNIFORM_NOISE_SPREAD,
                f"uniform noise_count needs noise_per_turn >= {UNIFORM_NOISE_SPREAD}",
            )

    def _check_shift(self) -> None:
        _require(self.n_turns >= 1, f"n_turns must be >= 1, got {self.n_turns}")
        _require(
            self.noise_per_turn >= 1, f"noise_per_turn must be >= 1, got {self.noise_per_turn}"
        )
        _require(self.count_scale > 0, f"count_scale must be > 0, got {self.count_scale}")

    def _check_attacks(self) -> None:
        _require(
            len(self.attack_count_choices) > 0 and min(self.attack_count_choices) >= 1,
            f"attack_count_choices must be non-empty and >= 1, got {self.attack_count_choices}",
        )
        _require(
            0 <= self.max_start_turn < self.n_turns,
            f"max_start_turn must be in [0, n_turns), got {self.max_start_turn}",
        )
        _require(0.0 <= self.p_advance <= 1.0, f"p_advance must be in [0, 1], got {self.p_advance}")

    @staticmethod
    def _check_probs(name: str, probs: tuple[float, ...]) -> None:
        _require(
            len(probs) == N_IMPORTANCE and min(probs) >= 0 and math.isclose(sum(probs), 1.0),
            f"{name} must be {N_IMPORTANCE} non-negative values summing to 1, got {probs}",
        )

    def _check_points(self) -> None:
        for name in ("reward_contain_early", "reward_contain_stage3", "reward_open_impact"):
            _require(getattr(self, name) >= 0, f"{name} must be >= 0")
        for name in ("penalty_impact", "penalty_running_at_end"):
            _require(getattr(self, name) <= 0, f"{name} must be <= 0")


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(f"TriageConfig: {message}")
