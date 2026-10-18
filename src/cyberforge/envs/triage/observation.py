"""What the agent sees (spec §5): inbox -> 49 numbers, and the action mask."""

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from cyberforge.envs.triage.catalogue import N_RULES
from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.types import MAX_STAGE, N_IMPORTANCE, Alert

WAITING_SIZE = N_RULES * N_IMPORTANCE  # [0:36]
ARRIVED_START = WAITING_SIZE  # [36:48]
TURN_INDEX = ARRIVED_START + N_RULES  # [48]
OBS_SIZE = TURN_INDEX + 1


def encode_observation(
    inbox: Iterable[Alert],
    arrived: Iterable[Alert],
    turn: int,
    config: TriageConfig,
) -> NDArray[np.float32]:
    """Waiting counts per (type, importance), arrivals per type, then turn / n_turns."""
    counts = np.zeros(OBS_SIZE, dtype=np.int64)
    for alert in inbox:
        counts[alert.rule_index * N_IMPORTANCE + alert.importance - 1] += 1
    for alert in arrived:
        counts[ARRIVED_START + alert.rule_index] += 1
    obs = _scale(counts, config)
    obs[TURN_INDEX] = turn / config.n_turns
    return obs


def observation_high(config: TriageConfig) -> NDArray[np.float32]:
    """Largest value each of the 49 numbers can take with this config."""
    max_attacks = max(config.attack_count_choices)
    arrival_rounds = config.n_turns + 1  # at reset, then after every step
    # Each attack raises one alert per stage it enters: at most MAX_STAGE in a shift,
    # and at most one of any given type per turn (stages use different types).
    max_waiting = arrival_rounds * config.noise_per_turn + max_attacks * MAX_STAGE
    max_arrived = config.noise_per_turn + max_attacks
    counts = np.zeros(OBS_SIZE, dtype=np.int64)
    counts[:WAITING_SIZE] = max_waiting
    counts[ARRIVED_START:TURN_INDEX] = max_arrived
    high = _scale(counts, config)
    high[TURN_INDEX] = 1.0
    return high


def action_mask(inbox: Iterable[Alert]) -> NDArray[np.bool_]:
    """True for each alert type with at least one alert waiting."""
    mask = np.zeros(N_RULES, dtype=np.bool_)
    for alert in inbox:
        mask[alert.rule_index] = True
    return mask


def _scale(counts: NDArray[np.int64], config: TriageConfig) -> NDArray[np.float32]:
    """Scale once (not += 0.1 per alert) so a full box never drifts past its max."""
    return counts.astype(np.float32) * np.float32(config.count_scale)
