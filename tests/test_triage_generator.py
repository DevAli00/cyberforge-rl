"""Spec §4.1-4.3: random false alarms and attacks. Checked against the catalogue and config
values (not hard-coded numbers), so tuning those keeps these tests valid."""

from collections import Counter

import numpy as np
import pytest

from cyberforge.envs.triage.catalogue import CATALOGUE, N_RULES, RULES_BY_STAGE
from cyberforge.envs.triage.config import NoiseCount, TriageConfig
from cyberforge.envs.triage.generator import (
    draw_attacks,
    draw_false_alarms,
    draw_noise_count,
    shuffle_arrivals,
    start_attack,
    try_advance,
)
from cyberforge.envs.triage.types import MAX_STAGE, Attack, AttackStatus

CONFIG = TriageConfig()
FIXED = TriageConfig(noise_count=NoiseCount.FIXED)  # exactly noise_per_turn false alarms
TOLERANCE = 0.015  # on shares estimated from tens of thousands of draws


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def _shares(values: list[int], keys: range) -> list[float]:
    counts = Counter(values)
    return [counts[key] / len(values) for key in keys]


def _active(stage: int = 1, importance: int = 3) -> Attack:
    return Attack(
        attack_id=7, start_turn=0, importance=importance, stage=stage, status=AttackStatus.ACTIVE
    )


# --- draw_attacks ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_draw_attacks_shape(seed: int) -> None:
    attacks = draw_attacks(_rng(seed), CONFIG)
    assert len(attacks) in CONFIG.attack_count_choices
    assert [a.attack_id for a in attacks] == list(range(len(attacks)))
    for attack in attacks:
        assert 0 <= attack.start_turn <= CONFIG.max_start_turn
        assert attack.status is AttackStatus.PENDING
        assert attack.stage == 0


def test_draw_attacks_distributions() -> None:
    rng = _rng()
    shifts = [draw_attacks(rng, CONFIG) for _ in range(20_000)]
    counts = _shares([len(s) for s in shifts], range(5))
    for n in CONFIG.attack_count_choices:
        assert counts[n] == pytest.approx(1 / len(CONFIG.attack_count_choices), abs=TOLERANCE)
    attacks = [a for s in shifts for a in s]
    importance = _shares([a.importance for a in attacks], range(1, 4))
    assert importance == pytest.approx(list(CONFIG.attack_importance_probs), abs=TOLERANCE)
    starts = _shares([a.start_turn for a in attacks], range(CONFIG.max_start_turn + 1))
    assert starts == pytest.approx([1 / (CONFIG.max_start_turn + 1)] * len(starts), abs=TOLERANCE)


# --- draw_false_alarms ----------------------------------------------------------------------


def test_draw_false_alarms_shape() -> None:
    alarms = draw_false_alarms(_rng(), FIXED, turn=4, first_id=37)
    assert len(alarms) == FIXED.noise_per_turn
    assert [a.alert_id for a in alarms] == list(range(37, 37 + FIXED.noise_per_turn))
    assert all(a.turn == 4 and a.is_false_alarm for a in alarms)


def test_draw_false_alarms_distributions() -> None:
    rng = _rng()
    alarms = [a for _ in range(10_000) for a in draw_false_alarms(rng, CONFIG, 0, 0)]
    types = _shares([a.rule_index for a in alarms], range(N_RULES))
    assert types == pytest.approx([rule.noise_freq for rule in CATALOGUE], abs=TOLERANCE)
    importance = _shares([a.importance for a in alarms], range(1, 4))
    assert importance == pytest.approx(list(CONFIG.noise_importance_probs), abs=TOLERANCE)


@pytest.mark.parametrize("noise_count", list(NoiseCount))
def test_at_least_one_false_alarm_every_turn(noise_count: NoiseCount) -> None:
    """An empty turn could leave nothing to open (E5 crash). Average 1 makes 0 very likely."""
    config = TriageConfig(
        noise_per_turn=1 if noise_count is not NoiseCount.UNIFORM else 3, noise_count=noise_count
    )
    rng = _rng()
    assert min(draw_noise_count(rng, config) for _ in range(5_000)) >= 1


# --- start_attack ---------------------------------------------------------------------------


def test_start_attack_enters_stage_1_with_one_alert() -> None:
    pending = Attack(attack_id=2, start_turn=3, importance=2)
    started, alert = start_attack(_rng(), pending, turn=3, alert_id=50)
    assert started.status is AttackStatus.ACTIVE
    assert started.stage == 1
    assert (started.attack_id, started.start_turn, started.importance) == (2, 3, 2)
    assert alert.rule_index in RULES_BY_STAGE[1]
    assert (alert.alert_id, alert.turn, alert.importance, alert.attack_id) == (50, 3, 2, 2)


def test_start_attack_refuses_a_started_attack() -> None:
    with pytest.raises(ValueError, match=r"pending"):
        start_attack(_rng(), _active(), turn=0, alert_id=0)


def test_start_alert_type_follows_attack_weights() -> None:
    rng = _rng()
    pending = Attack(attack_id=0, start_turn=0, importance=1)
    alerts = [start_attack(rng, pending, 0, 0)[1] for _ in range(20_000)]
    shares = _shares([a.rule_index for a in alerts], range(N_RULES))
    for rule_index in RULES_BY_STAGE[1]:
        assert shares[rule_index] == pytest.approx(
            CATALOGUE[rule_index].attack_weight, abs=TOLERANCE
        )


def test_stage_alert_type_is_picked_evenly_among_the_stage_types() -> None:
    rng = _rng()
    types = [
        try_advance(rng, _active(stage=1), TriageConfig(p_advance=1.0), 0, 0)[1]
        for _ in range(4_000)
    ]
    shares = _shares([a.rule_index for a in types if a is not None], range(N_RULES))
    for rule_index in RULES_BY_STAGE[2]:
        assert shares[rule_index] == pytest.approx(1 / len(RULES_BY_STAGE[2]), abs=0.03)


# --- try_advance ----------------------------------------------------------------------------


@pytest.mark.parametrize("stage", range(1, MAX_STAGE))
def test_advance_always_when_p_is_1(stage: int) -> None:
    attack = _active(stage=stage, importance=3)
    moved, alert = try_advance(_rng(), attack, TriageConfig(p_advance=1.0), turn=5, alert_id=9)
    assert moved.stage == stage + 1
    assert moved.status is AttackStatus.ACTIVE
    assert alert is not None
    assert alert.rule_index in RULES_BY_STAGE[stage + 1]
    assert (alert.alert_id, alert.turn, alert.importance, alert.attack_id) == (9, 5, 3, 7)


def test_advance_never_when_p_is_0() -> None:
    attack = _active(stage=2)
    assert try_advance(_rng(), attack, TriageConfig(p_advance=0.0), 0, 0) == (attack, None)


@pytest.mark.parametrize(
    "attack",
    [
        _active(stage=MAX_STAGE),
        Attack(attack_id=0, start_turn=0, importance=1),
        Attack(attack_id=0, start_turn=0, importance=1, stage=2, status=AttackStatus.CONTAINED),
    ],
    ids=["ransomware", "pending", "contained"],
)
def test_advance_does_nothing_for_finished_or_waiting_attacks(attack: Attack) -> None:
    assert try_advance(_rng(), attack, TriageConfig(p_advance=1.0), 0, 0) == (attack, None)


def test_advance_rate_matches_p_advance() -> None:
    rng = _rng()
    moved = [try_advance(rng, _active(), CONFIG, 0, 0)[1] is not None for _ in range(20_000)]
    assert np.mean(moved) == pytest.approx(CONFIG.p_advance, abs=TOLERANCE)


# --- randomness -----------------------------------------------------------------------------


def test_same_seed_same_draws() -> None:
    def draw(seed: int) -> tuple[object, ...]:
        rng = _rng(seed)
        return (draw_attacks(rng, CONFIG), draw_false_alarms(rng, CONFIG, 0, 0))

    assert draw(5) == draw(5)
    assert draw(5) != draw(6)


def test_global_numpy_random_is_never_used() -> None:
    np.random.seed(0)
    first = draw_false_alarms(_rng(1), CONFIG, 0, 0)
    np.random.seed(999)
    assert draw_false_alarms(_rng(1), CONFIG, 0, 0) == first


def test_shuffle_arrivals_keeps_alerts_and_ids() -> None:
    alerts = draw_false_alarms(_rng(), CONFIG, turn=2, first_id=40)
    shuffled = shuffle_arrivals(_rng(1), alerts)
    assert [a.alert_id for a in shuffled] == [a.alert_id for a in alerts]  # same ids, in order
    strip = lambda a: (a.rule_index, a.importance, a.turn, a.attack_id)  # noqa: E731
    assert sorted(map(strip, shuffled)) == sorted(map(strip, alerts))  # same alerts


def test_shuffle_arrivals_mixes_the_order() -> None:
    alerts = tuple(draw_false_alarms(_rng(), TriageConfig(noise_per_turn=30), 0, 0))
    assert shuffle_arrivals(_rng(1), alerts) != alerts


# --- draw_noise_count -----------------------------------------------------------------------


def test_fixed_noise_count_is_always_the_average_and_uses_no_dice() -> None:
    rng = _rng()
    before = rng.bit_generator.state
    assert {draw_noise_count(rng, FIXED) for _ in range(100)} == {FIXED.noise_per_turn}
    assert rng.bit_generator.state == before  # keeps earlier fixed-count results reproducible


@pytest.mark.parametrize(
    ("noise_count", "variance"),
    [(NoiseCount.BINOMIAL, 4.5), (NoiseCount.POISSON, 9.0), (NoiseCount.UNIFORM, 4.0)],
)
def test_varying_noise_count_shape(noise_count: NoiseCount, variance: float) -> None:
    config = TriageConfig(noise_count=noise_count)
    rng = _rng()
    counts = np.array([draw_noise_count(rng, config) for _ in range(40_000)])
    assert counts.mean() == pytest.approx(config.noise_per_turn, abs=0.1)
    assert counts.var() == pytest.approx(variance, rel=0.08)
    assert counts.min() >= 0
    assert counts.max() <= config.max_noise_per_turn


def test_uniform_noise_count_covers_6_to_12_evenly() -> None:
    config = TriageConfig(noise_count=NoiseCount.UNIFORM)
    rng = _rng()
    counts = [draw_noise_count(rng, config) for _ in range(14_000)]
    assert set(counts) == set(range(6, 13))
    assert _shares(counts, range(6, 13)) == pytest.approx([1 / 7] * 7, abs=TOLERANCE)


def test_draw_false_alarms_uses_the_drawn_count() -> None:
    config = TriageConfig(noise_count=NoiseCount.POISSON)
    for seed in range(20):
        expected = draw_noise_count(_rng(seed), config)
        assert len(draw_false_alarms(_rng(seed), config, 0, 0)) == expected
