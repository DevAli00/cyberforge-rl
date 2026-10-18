"""Data types shared by the triage game and its players (spec §5). All frozen."""

from dataclasses import dataclass
from enum import StrEnum

MIN_SEVERITY, MAX_SEVERITY = 1, 5
MAX_STAGE = 4  # 1 gets in, 2 settles in, 3 spreads, 4 ransomware
N_IMPORTANCE = 3  # machine importance 1, 2 or 3


class Source(StrEnum):
    """Which sensor raised the alert."""

    EMAIL = "email"
    IDENTITY = "identity"
    CLOUD = "cloud"
    IDS = "ids"
    EDR = "edr"


class AttackStatus(StrEnum):
    PENDING = "pending"  # start turn not reached yet, stage 0
    ACTIVE = "active"  # running, stage 1-4
    CONTAINED = "contained"  # stopped by opening one of its alerts


class InvalidActionError(ValueError):
    """The action is out of range or its alert type has nothing waiting (mask is false)."""


def _require(ok: bool, owner: str, message: str) -> None:
    if not ok:
        raise ValueError(f"{owner}: {message}")


def _valid_importance(importance: int) -> bool:
    return 1 <= importance <= N_IMPORTANCE


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """One alert type (one row of spec §4.3)."""

    rule_id: str
    severity: int
    source: Source
    stage: int | None  # attack stage that raises it, None = only ever a false alarm
    noise_freq: float  # share of false alarms that are of this type
    attack_weight: float  # chance an attack entering `stage` raises this type (0 if no stage)

    def __post_init__(self) -> None:
        _require(bool(self.rule_id), "RuleSpec", "rule_id must not be empty")
        _require(
            MIN_SEVERITY <= self.severity <= MAX_SEVERITY,
            "RuleSpec",
            f"severity must be {MIN_SEVERITY}-{MAX_SEVERITY}, got {self.severity}",
        )
        _require(
            self.stage is None or 1 <= self.stage <= MAX_STAGE,
            "RuleSpec",
            f"stage must be None or 1-{MAX_STAGE}, got {self.stage}",
        )
        _require(
            0.0 <= self.noise_freq <= 1.0,
            "RuleSpec",
            f"noise_freq must be in [0, 1], got {self.noise_freq}",
        )
        if self.stage is None:
            _require(self.attack_weight == 0, "RuleSpec", "a noise-only type has attack_weight 0")
        else:
            _require(
                0 < self.attack_weight <= 1,
                "RuleSpec",
                f"attack_weight must be in (0, 1], got {self.attack_weight}",
            )


@dataclass(frozen=True, slots=True)
class Alert:
    """One line in the SOC inbox."""

    alert_id: int
    rule_index: int  # row in CATALOGUE, same number as the action
    importance: int  # importance of the machine it fired on, 1-3
    turn: int  # step index it arrived on
    attack_id: int | None = None  # None = false alarm

    def __post_init__(self) -> None:
        _require(self.alert_id >= 0, "Alert", f"alert_id must be >= 0, got {self.alert_id}")
        _require(self.rule_index >= 0, "Alert", f"rule_index must be >= 0, got {self.rule_index}")
        _require(
            _valid_importance(self.importance),
            "Alert",
            f"importance must be 1-{N_IMPORTANCE}, got {self.importance}",
        )
        _require(self.turn >= 0, "Alert", f"turn must be >= 0, got {self.turn}")

    @property
    def is_false_alarm(self) -> bool:
        return self.attack_id is None


@dataclass(frozen=True, slots=True)
class Attack:
    """One hidden attacker moving through stages 1-4."""

    attack_id: int
    start_turn: int
    importance: int  # importance of the target machine, 1-3
    stage: int = 0
    status: AttackStatus = AttackStatus.PENDING

    def __post_init__(self) -> None:
        _require(self.attack_id >= 0, "Attack", f"attack_id must be >= 0, got {self.attack_id}")
        _require(self.start_turn >= 0, "Attack", f"start_turn must be >= 0, got {self.start_turn}")
        _require(
            _valid_importance(self.importance),
            "Attack",
            f"importance must be 1-{N_IMPORTANCE}, got {self.importance}",
        )
        if self.status is AttackStatus.PENDING:
            _require(self.stage == 0, "Attack", f"a pending attack is stage 0, got {self.stage}")
        else:
            _require(
                1 <= self.stage <= MAX_STAGE,
                "Attack",
                f"a started attack is stage 1-{MAX_STAGE}, got {self.stage}",
            )

    @property
    def reached_impact(self) -> bool:
        return self.stage == MAX_STAGE


@dataclass(frozen=True, slots=True)
class HiddenView:
    """Read-only snapshot of the truth. Only the oracle may use it."""

    turn: int
    attacks: tuple[Attack, ...]
    inbox: tuple[Alert, ...]  # every waiting alert, attack_id says which attack it belongs to

    def alerts_of(self, attack_id: int) -> tuple[Alert, ...]:
        return tuple(alert for alert in self.inbox if alert.attack_id == attack_id)


@dataclass(frozen=True, slots=True)
class ShiftStats:
    """Running totals for the current shift, exposed as `info` (spec §5)."""

    attacks_total: int = 0
    contained_early: int = 0  # stopped at stage 1-2
    contained_stage3: int = 0
    reached_impact: int = 0
    false_alarms: int = 0

    def __post_init__(self) -> None:
        for name, value in self.as_info().items():
            _require(value >= 0, "ShiftStats", f"{name} must be >= 0, got {value}")

    def as_info(self) -> dict[str, int]:
        return {
            "attacks_total": self.attacks_total,
            "contained_early": self.contained_early,
            "contained_stage3": self.contained_stage3,
            "reached_impact": self.reached_impact,
            "false_alarms": self.false_alarms,
        }
