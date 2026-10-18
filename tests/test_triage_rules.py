"""Spec §4.4-4.5: the turn rules.

`opened_alert` is wiring (Claude). `contain`, `containment_points`, `impact_points` and
`end_of_shift_points` are hand-written by Ali: these tests say what they must do.
"""

import pytest

from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.rules import (
    contain,
    containment_points,
    end_of_shift_points,
    impact_points,
    opened_alert,
)
from cyberforge.envs.triage.types import Alert, Attack, AttackStatus

CONFIG = TriageConfig()


def _alert(
    alert_id: int, importance: int = 1, turn: int = 0, attack_id: int | None = None, rule: int = 0
) -> Alert:
    return Alert(
        alert_id=alert_id, rule_index=rule, importance=importance, turn=turn, attack_id=attack_id
    )


def _attack(attack_id: int, stage: int, status: AttackStatus = AttackStatus.ACTIVE) -> Attack:
    if status is AttackStatus.PENDING:
        return Attack(attack_id=attack_id, start_turn=5, importance=2)
    return Attack(attack_id=attack_id, start_turn=0, importance=2, stage=stage, status=status)


# --- opened_alert (Claude) ------------------------------------------------------------------


def test_opens_most_important_machine_first() -> None:
    inbox = (
        _alert(0, importance=1, turn=5),
        _alert(1, importance=3, turn=0),
        _alert(2, importance=2),
    )
    assert opened_alert(inbox, 0).alert_id == 1


def test_then_most_recent() -> None:
    inbox = (
        _alert(0, importance=3, turn=1),
        _alert(1, importance=3, turn=4),
        _alert(2, importance=3, turn=2),
    )
    assert opened_alert(inbox, 0).alert_id == 1


def test_then_lowest_id() -> None:
    inbox = (
        _alert(7, importance=3, turn=4),
        _alert(3, importance=3, turn=4),
        _alert(9, importance=3, turn=4),
    )
    assert opened_alert(inbox, 0).alert_id == 3


def test_only_alerts_of_the_requested_type() -> None:
    inbox = (_alert(0, importance=3, rule=5), _alert(1, importance=1, rule=2))
    assert opened_alert(inbox, 2).alert_id == 1


def test_no_alert_of_that_type_raises() -> None:
    with pytest.raises(ValueError, match=r"type 4"):
        opened_alert((_alert(0, rule=0),), 4)


# --- contain (Ali) --------------------------------------------------------------------------
# The env removes the opened alert from the inbox first, then calls contain() with the rest.


def test_contain_false_alarm_changes_nothing() -> None:
    attacks = (_attack(0, stage=2),)
    rest = (_alert(1, attack_id=0), _alert(2))
    assert contain(_alert(9), attacks, rest) == (attacks, rest)


def test_contain_stops_the_attack_and_removes_its_alerts() -> None:
    attacks = (_attack(0, stage=2), _attack(1, stage=1))
    rest = (_alert(1, attack_id=0), _alert(2), _alert(3, attack_id=1), _alert(4, attack_id=0))
    new_attacks, new_inbox = contain(_alert(9, attack_id=0), attacks, rest)
    assert new_attacks == (
        _attack(0, stage=2, status=AttackStatus.CONTAINED),  # same stage, now stopped
        attacks[1],  # other attack untouched
    )
    assert new_inbox == (_alert(2), _alert(3, attack_id=1))  # order kept


def test_contain_also_stops_an_attack_already_at_ransomware() -> None:
    attacks = (_attack(0, stage=4),)
    new_attacks, _ = contain(_alert(9, attack_id=0), attacks, ())
    assert new_attacks[0].status is AttackStatus.CONTAINED
    assert new_attacks[0].stage == 4


def test_contain_returns_new_tuples() -> None:
    attacks = (_attack(0, stage=1),)
    contain(_alert(9, attack_id=0), attacks, ())
    assert attacks[0].status is AttackStatus.ACTIVE  # input not changed


# --- containment_points (Ali) ---------------------------------------------------------------


@pytest.mark.parametrize(("stage", "points"), [(1, 1.0), (2, 1.0), (3, 0.5), (4, 0.2)])
def test_containment_points_by_stage(stage: int, points: float) -> None:
    assert containment_points(stage, CONFIG) == pytest.approx(points)


def test_containment_points_follow_config() -> None:
    config = TriageConfig(
        reward_contain_early=2.0, reward_contain_stage3=0.7, reward_open_impact=0.1
    )
    assert [containment_points(s, config) for s in (1, 2, 3, 4)] == pytest.approx(
        [2.0, 2.0, 0.7, 0.1]
    )


@pytest.mark.parametrize("stage", [0, 5])
def test_containment_points_reject_impossible_stage(stage: int) -> None:
    with pytest.raises(ValueError, match=r"stage"):
        containment_points(stage, CONFIG)


# --- impact_points (Ali) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "points"),
    [(3, 4, -5.0), (2, 3, 0.0), (1, 1, 0.0), (4, 4, 0.0)],
    ids=["reaches ransomware", "advances below 4", "stays", "already at 4"],
)
def test_impact_points(before: int, after: int, points: float) -> None:
    assert impact_points(_attack(0, before), _attack(0, after), CONFIG) == pytest.approx(points)


def test_impact_points_follow_config() -> None:
    config = TriageConfig(penalty_impact=-8.0)
    assert impact_points(_attack(0, 3), _attack(0, 4), config) == pytest.approx(-8.0)


# --- end_of_shift_points (Ali) --------------------------------------------------------------


def test_end_of_shift_minus_one_per_attack_still_running_below_4() -> None:
    attacks = (
        _attack(0, stage=1),  # running: -1
        _attack(1, stage=3),  # running: -1
        _attack(2, stage=4),  # already paid -5, not counted
        _attack(3, stage=2, status=AttackStatus.CONTAINED),  # stopped, not counted
    )
    assert end_of_shift_points(attacks, CONFIG) == pytest.approx(-2.0)


def test_end_of_shift_nothing_running() -> None:
    assert end_of_shift_points((), CONFIG) == 0.0


def test_end_of_shift_follows_config() -> None:
    config = TriageConfig(penalty_running_at_end=-3.0)
    assert end_of_shift_points((_attack(0, stage=2),), config) == pytest.approx(-3.0)
