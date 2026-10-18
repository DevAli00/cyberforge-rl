"""Tests for the learned bandit of spec §6, written before it exists.

They fail until `cyberforge.agents.bandit.LearnedBandit` exists with:
- `LearnedBandit(n_actions=12, epsilon=0.1)`, `name = "learned_bandit"`;
- `values` and `counts`: float arrays of shape (n_actions,), starting at 0;
- `update(action, reward)`: the running average of the points of each alert type
  (the rule Rayane writes by hand);
- `act(obs, action_mask, rng)`: with probability epsilon any allowed type at random,
  otherwise the allowed type with the highest average.
"""

import importlib
from typing import Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from numpy.typing import NDArray

from cyberforge.agents.base import LearningPolicy
from tests.fakes import N_TYPES, OBS_SIZE, FakeTriageEnv
from tests.test_policies import inboxes

OBS = np.zeros(OBS_SIZE, dtype=np.float32)
ALL_ALLOWED = np.ones(N_TYPES, dtype=np.bool_)


def make_bandit(epsilon: float = 0.1) -> Any:
    # Imported per test so that, until the bandit exists, only these tests fail.
    bandit_module = importlib.import_module("cyberforge.agents.bandit")
    return bandit_module.LearnedBandit(n_actions=N_TYPES, epsilon=epsilon)


def mask_of(*actions: int) -> NDArray[np.bool_]:
    mask = np.zeros(N_TYPES, dtype=np.bool_)
    mask[list(actions)] = True
    return mask


def test_bandit_starts_with_zero_values_and_counts() -> None:
    bandit = make_bandit()
    assert bandit.name == "learned_bandit"
    np.testing.assert_array_equal(bandit.values, np.zeros(N_TYPES))
    np.testing.assert_array_equal(bandit.counts, np.zeros(N_TYPES))


def test_bandit_is_a_learning_policy() -> None:
    bandit: LearningPolicy = make_bandit()
    assert callable(bandit.update)


# Update rule: running average of the points per alert type.


def test_update_keeps_the_running_average_of_one_type() -> None:
    bandit = make_bandit()
    for reward in [1.0, 0.0, 0.5]:
        bandit.update(3, reward)
    assert bandit.counts[3] == 3
    assert bandit.values[3] == pytest.approx(0.5)
    # Other types are untouched.
    assert np.all(np.delete(bandit.counts, 3) == 0)
    assert np.all(np.delete(bandit.values, 3) == 0)


@given(
    history=st.lists(
        st.tuples(st.integers(0, N_TYPES - 1), st.sampled_from([0.0, 0.2, 0.5, 1.0, -5.0, -1.0])),
        max_size=200,
    )
)
def test_update_matches_the_mean_of_all_points_received(
    history: list[tuple[int, float]],
) -> None:
    bandit = make_bandit()
    for action, reward in history:
        bandit.update(action, reward)
    for action in range(N_TYPES):
        rewards = [r for a, r in history if a == action]
        assert bandit.counts[action] == len(rewards)
        expected = float(np.mean(rewards)) if rewards else 0.0
        assert bandit.values[action] == pytest.approx(expected, abs=1e-9)


# Choice: epsilon-greedy among allowed types.


def test_greedy_bandit_picks_the_best_allowed_type() -> None:
    bandit = make_bandit(epsilon=0.0)
    bandit.update(0, 1.0)  # best overall, but masked below
    bandit.update(5, 0.5)
    bandit.update(7, 0.2)
    rng = np.random.default_rng(0)
    for _ in range(50):
        assert bandit.act(OBS, mask_of(5, 7, 9), rng) == 5


def test_greedy_bandit_prefers_an_untried_type_over_a_negative_one() -> None:
    bandit = make_bandit(epsilon=0.0)
    bandit.update(2, -5.0)
    assert bandit.act(OBS, mask_of(2, 4), np.random.default_rng(0)) == 4


def test_fully_exploring_bandit_tries_every_allowed_type() -> None:
    bandit = make_bandit(epsilon=1.0)
    bandit.update(5, 1.0)
    rng = np.random.default_rng(0)
    mask = mask_of(1, 5, 8)
    picks = {bandit.act(OBS, mask, rng) for _ in range(200)}
    assert picks == {1, 5, 8}


def test_bandit_explores_about_epsilon_of_the_time() -> None:
    bandit = make_bandit(epsilon=0.2)
    bandit.update(5, 1.0)
    rng = np.random.default_rng(0)
    mask = mask_of(1, 5, 8, 10)
    n = 4000
    greedy_share = sum(bandit.act(OBS, mask, rng) == 5 for _ in range(n)) / n
    # Greedy 80% of the time, plus 1 chance in 4 when exploring: 0.85.
    assert greedy_share == pytest.approx(0.85, abs=0.03)


@given(
    inbox=inboxes(),
    values=st.lists(st.floats(-5, 1), min_size=N_TYPES, max_size=N_TYPES),
    epsilon=st.sampled_from([0.0, 0.1, 1.0]),
    seed=st.integers(0, 2**32 - 1),
)
def test_bandit_only_picks_allowed_actions(
    inbox: tuple[NDArray[np.float32], NDArray[np.bool_]],
    values: list[float],
    epsilon: float,
    seed: int,
) -> None:
    obs, mask = inbox
    bandit = make_bandit(epsilon=epsilon)
    for action, value in enumerate(values):
        bandit.update(action, value)
    action = bandit.act(obs, mask, np.random.default_rng(seed))
    assert isinstance(action, int)
    assert mask[action]


def test_bandit_learns_during_a_shift_on_fake_env() -> None:
    env = FakeTriageEnv()
    bandit = make_bandit()
    rng = np.random.default_rng(0)
    obs, _ = env.reset(seed=3)
    terminated = False
    steps = 0
    while not terminated:
        action = bandit.act(obs, env.action_masks(), rng)
        obs, reward, terminated, _, _ = env.step(action)
        bandit.update(action, float(reward))
        steps += 1
    assert bandit.counts.sum() == steps == 10
