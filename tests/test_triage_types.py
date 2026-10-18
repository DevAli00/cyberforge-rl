"""Spec §5: the frozen data types shared by the game and the players."""

import dataclasses

import pytest

from cyberforge.envs.triage.types import (
    Alert,
    Attack,
    AttackStatus,
    HiddenView,
    InvalidActionError,
    RuleSpec,
    ShiftStats,
    Source,
)

INFO_KEYS = {
    "attacks_total",
    "contained_early",
    "contained_stage3",
    "reached_impact",
    "false_alarms",
}


def _rule(**overrides: object) -> RuleSpec:
    fields: dict[str, object] = {
        "rule_id": "x",
        "severity": 3,
        "source": Source.EDR,
        "stage": 1,
        "noise_freq": 0.1,
        "attack_weight": 1.0,
    }
    return RuleSpec(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "obj",
    [
        _rule(),
        Alert(alert_id=0, rule_index=0, importance=1, turn=0),
        Attack(attack_id=0, start_turn=0, importance=3),
        HiddenView(turn=0, attacks=(), inbox=()),
        ShiftStats(),
    ],
)
def test_types_are_frozen(obj: object) -> None:
    field = dataclasses.fields(obj)[0].name  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, 99)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rule_id": ""},
        {"severity": 0},
        {"severity": 6},
        {"stage": 0},
        {"stage": 5},
        {"noise_freq": -0.1},
        {"noise_freq": 1.1},
        {"attack_weight": -0.1},
        {"attack_weight": 1.1},
        {"attack_weight": 0.0},  # a stage type must be pickable
        {"stage": None, "attack_weight": 0.5},  # a noise-only type cannot be picked by attacks
    ],
)
def test_rule_spec_rejects_bad_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"RuleSpec"):
        _rule(**overrides)


def test_rule_spec_accepts_noise_only_rule() -> None:
    assert _rule(stage=None, attack_weight=0.0).stage is None


def test_alert_false_alarm_flag() -> None:
    assert Alert(alert_id=1, rule_index=0, importance=1, turn=0).is_false_alarm
    assert not Alert(alert_id=2, rule_index=0, importance=1, turn=0, attack_id=7).is_false_alarm


@pytest.mark.parametrize(
    "overrides",
    [{"alert_id": -1}, {"rule_index": -1}, {"importance": 0}, {"importance": 4}, {"turn": -1}],
)
def test_alert_rejects_bad_values(overrides: dict[str, int]) -> None:
    fields = {"alert_id": 0, "rule_index": 0, "importance": 1, "turn": 0} | overrides
    with pytest.raises(ValueError, match=r"Alert"):
        Alert(**fields)


def test_attack_defaults_to_not_started() -> None:
    attack = Attack(attack_id=0, start_turn=2, importance=2)
    assert attack.status is AttackStatus.PENDING
    assert attack.stage == 0
    assert not attack.reached_impact


def test_attack_reached_impact_at_stage_4() -> None:
    attack = Attack(attack_id=0, start_turn=0, importance=1, stage=4, status=AttackStatus.ACTIVE)
    assert attack.reached_impact


@pytest.mark.parametrize(
    ("stage", "status"),
    [
        (1, AttackStatus.PENDING),  # not started yet must be stage 0
        (0, AttackStatus.ACTIVE),  # started must be stage 1-4
        (0, AttackStatus.CONTAINED),
        (5, AttackStatus.ACTIVE),
    ],
)
def test_attack_rejects_inconsistent_stage(stage: int, status: AttackStatus) -> None:
    with pytest.raises(ValueError, match=r"Attack"):
        Attack(attack_id=0, start_turn=0, importance=1, stage=stage, status=status)


@pytest.mark.parametrize("overrides", [{"importance": 0}, {"start_turn": -1}, {"attack_id": -1}])
def test_attack_rejects_bad_values(overrides: dict[str, int]) -> None:
    fields = {"attack_id": 0, "start_turn": 0, "importance": 1} | overrides
    with pytest.raises(ValueError, match=r"Attack"):
        Attack(**fields)


def test_hidden_view_alerts_of() -> None:
    real = Alert(alert_id=1, rule_index=0, importance=3, turn=0, attack_id=5)
    noise = Alert(alert_id=2, rule_index=6, importance=1, turn=0)
    view = HiddenView(turn=0, attacks=(), inbox=(real, noise))
    assert view.alerts_of(5) == (real,)
    assert view.alerts_of(6) == ()


def test_invalid_action_error_is_value_error() -> None:
    assert issubclass(InvalidActionError, ValueError)


def test_shift_stats_info_has_spec_keys() -> None:
    info = ShiftStats().as_info()
    assert set(info) == INFO_KEYS
    assert all(value == 0 for value in info.values())


def test_shift_stats_info_is_a_fresh_dict() -> None:
    stats = ShiftStats()
    assert stats.as_info() is not stats.as_info()


def test_shift_stats_rejects_negative() -> None:
    with pytest.raises(ValueError, match=r"ShiftStats"):
        ShiftStats(false_alarms=-1)
