"""Spec §5: observation layout and action mask."""

import numpy as np

from cyberforge.envs.triage.config import NoiseCount, TriageConfig
from cyberforge.envs.triage.observation import (
    OBS_SIZE,
    action_mask,
    encode_observation,
    observation_high,
)
from cyberforge.envs.triage.types import Alert

CONFIG = TriageConfig()


def _alert(alert_id: int, rule_index: int, importance: int) -> Alert:
    return Alert(alert_id=alert_id, rule_index=rule_index, importance=importance, turn=0)


def test_obs_size_is_49() -> None:
    assert OBS_SIZE == 49


def test_empty_inbox_is_all_zeros() -> None:
    obs = encode_observation(inbox=(), arrived=(), turn=0, config=CONFIG)
    assert obs.shape == (49,)
    assert obs.dtype == np.float32
    assert not obs.any()


def test_waiting_counts_are_row_major_by_type() -> None:
    # type 2, importance 3 -> index 2 * 3 + (3 - 1) = 8
    inbox = (_alert(0, 2, 3), _alert(1, 2, 3), _alert(2, 0, 1))
    obs = encode_observation(inbox=inbox, arrived=(), turn=0, config=CONFIG)
    assert np.isclose(obs[8], 0.2)
    assert np.isclose(obs[0], 0.1)
    assert np.count_nonzero(obs) == 2


def test_arrivals_are_counted_per_type() -> None:
    arrived = (_alert(0, 11, 1), _alert(1, 11, 3))
    obs = encode_observation(inbox=arrived, arrived=arrived, turn=0, config=CONFIG)
    assert np.isclose(obs[36 + 11], 0.2)


def test_turn_is_scaled_by_shift_length() -> None:
    obs = encode_observation(inbox=(), arrived=(), turn=5, config=CONFIG)
    assert np.isclose(obs[48], 0.5)


def test_action_mask_true_only_for_waiting_types() -> None:
    mask = action_mask((_alert(0, 3, 1), _alert(1, 3, 2), _alert(2, 7, 1)))
    assert mask.shape == (12,)
    assert mask.dtype == np.bool_
    assert mask.nonzero()[0].tolist() == [3, 7]


def test_observation_high_default_config() -> None:
    # default Poisson: at most 18 false alarms per turn
    # waiting: (10 + 1) arrival rounds x 18 + 4 attacks x 4 stages = 214 alerts
    # arrived: 18 false alarms + 1 alert per attack = 22 per type
    high = observation_high(CONFIG)
    assert high.shape == (49,)
    assert high.dtype == np.float32
    assert np.allclose(high[:36], 21.4)
    assert np.allclose(high[36:48], 2.2)
    assert high[48] == 1.0


def test_observation_high_follows_config() -> None:
    config = TriageConfig(
        n_turns=4, max_start_turn=0, noise_per_turn=2, noise_count=NoiseCount.FIXED
    )
    high = observation_high(config)
    assert np.allclose(high[:36], (5 * 2 + 4 * 4) * 0.1)
    assert np.allclose(high[36:48], (2 + 4) * 0.1)


def test_worst_case_inbox_fits_under_high() -> None:
    """Counts are scaled once, so float32 drift can't push a full box past the max."""
    inbox = tuple(_alert(i, 0, 1) for i in range(115))
    obs = encode_observation(inbox=inbox, arrived=(), turn=10, config=CONFIG)
    assert obs[0] <= observation_high(CONFIG)[0]


def test_observation_high_uses_the_largest_noise_count() -> None:
    # waiting: 11 rounds x 18 false alarms + 4 attacks x 4 stages = 214; arrived: 18 + 4 = 22
    high = observation_high(TriageConfig(noise_count=NoiseCount.BINOMIAL))
    assert np.allclose(high[:36], 21.4)
    assert np.allclose(high[36:48], 2.2)
