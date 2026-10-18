"""Spec §5: the TriageEnv interface (skeleton, placeholder logic until #6 and #9)."""

import warnings
from collections import Counter

import numpy as np
import pytest
from gymnasium import spaces
from gymnasium.utils.env_checker import check_env

from cyberforge.envs.triage.catalogue import N_RULES
from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.env import TriageEnv
from cyberforge.envs.triage.observation import observation_high
from cyberforge.envs.triage.types import HiddenView, InvalidActionError

INFO_KEYS = {
    "attacks_total",
    "contained_early",
    "contained_stage3",
    "reached_impact",
    "false_alarms",
}


def _first_allowed(env: TriageEnv) -> int:
    return int(np.flatnonzero(env.action_masks())[0])


def test_passes_check_env() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_env(TriageEnv(), skip_render_check=True)


def test_spaces_match_spec() -> None:
    env = TriageEnv()
    assert env.action_space == spaces.Discrete(N_RULES)
    assert env.observation_space == spaces.Box(0.0, observation_high(env.config), (49,), np.float32)


def test_reset_returns_obs_and_info() -> None:
    obs, info = TriageEnv().reset(seed=0)
    assert obs.shape == (49,)
    assert obs.dtype == np.float32
    assert obs[48] == 0.0
    assert set(info) == INFO_KEYS


def test_shift_lasts_10_turns() -> None:
    env = TriageEnv()
    env.reset(seed=0)
    for turn in range(1, 11):
        obs, reward, terminated, truncated, info = env.step(_first_allowed(env))
        assert isinstance(reward, float)
        assert truncated is False
        assert terminated is (turn == 10)
        assert np.isclose(obs[48], turn / 10)
        assert set(info) == INFO_KEYS


def test_shift_length_follows_config() -> None:
    env = TriageEnv(TriageConfig(n_turns=3, max_start_turn=2))
    env.reset(seed=0)
    results = [env.step(_first_allowed(env))[2] for _ in range(3)]
    assert results == [False, False, True]


def test_step_before_reset_raises() -> None:
    with pytest.raises(RuntimeError, match=r"reset"):
        TriageEnv().step(0)


def test_step_after_shift_end_raises() -> None:
    env = TriageEnv(TriageConfig(n_turns=1, max_start_turn=0))
    env.reset(seed=0)
    env.step(_first_allowed(env))
    with pytest.raises(RuntimeError, match=r"reset"):
        env.step(_first_allowed(env))


@pytest.mark.parametrize("action", [2.0, True, "3"])
def test_non_integer_action_raises(action: object) -> None:
    env = TriageEnv()
    env.reset(seed=0)
    with pytest.raises(InvalidActionError):
        env.step(action)  # type: ignore[arg-type]


@pytest.mark.parametrize("action", [-1, N_RULES, 100])
def test_out_of_range_action_raises(action: int) -> None:
    env = TriageEnv()
    env.reset(seed=0)
    with pytest.raises(InvalidActionError):
        env.step(action)


def test_accepts_numpy_integer_action() -> None:
    env = TriageEnv()
    env.reset(seed=0)
    env.step(np.int64(_first_allowed(env)))


@pytest.mark.parametrize("seed", range(5))
def test_masked_actions_raise_and_change_nothing(seed: int) -> None:
    """Vacuous while the placeholder allows every type; becomes a real check after #6."""
    env = TriageEnv()
    env.reset(seed=seed)
    terminated = False
    while not terminated:
        before = env.hidden_view()
        for action in np.flatnonzero(~env.action_masks()):
            with pytest.raises(InvalidActionError):
                env.step(int(action))
            assert env.hidden_view() == before
        _, _, terminated, _, _ = env.step(_first_allowed(env))


def test_same_seed_same_shift() -> None:
    def play(seed: int) -> list[tuple[list[float], float]]:
        env = TriageEnv()
        obs, _ = env.reset(seed=seed)
        trace = [(obs.tolist(), 0.0)]
        terminated = False
        while not terminated:
            obs, reward, terminated, _, _ = env.step(_first_allowed(env))
            trace.append((obs.tolist(), float(reward)))
        return trace

    assert play(42) == play(42)


def test_observation_agrees_with_hidden_view() -> None:
    env = TriageEnv()
    obs, _ = env.reset(seed=0)
    for _ in range(3):
        view = env.hidden_view()
        counts = Counter((alert.rule_index, alert.importance) for alert in view.inbox)
        expected = np.zeros((N_RULES, 3), dtype=np.float32)
        for (rule_index, importance), count in counts.items():
            expected[rule_index, importance - 1] = count * 0.1
        assert np.allclose(obs[:36], expected.ravel())
        mask = np.zeros(N_RULES, dtype=np.bool_)
        mask[[alert.rule_index for alert in view.inbox]] = True
        assert np.array_equal(env.action_masks(), mask)
        obs, _, _, _, _ = env.step(_first_allowed(env))


def test_hidden_view_is_a_snapshot() -> None:
    env = TriageEnv()
    env.reset(seed=0)
    view = env.hidden_view()
    assert isinstance(view, HiddenView)
    assert view.turn == 0
    assert isinstance(view.attacks, tuple)
    assert isinstance(view.inbox, tuple)
    env.step(_first_allowed(env))
    assert view.turn == 0  # earlier snapshot did not change


def test_info_attacks_total_matches_hidden_view() -> None:
    env = TriageEnv()
    _, info = env.reset(seed=0)
    assert info["attacks_total"] == len(env.hidden_view().attacks)


def test_placeholder_inbox_piles_up() -> None:
    """Placeholder until #6/#9: one false alarm of every type arrives each turn, none are opened."""
    env = TriageEnv()
    env.reset(seed=0)
    assert len(env.hidden_view().inbox) == N_RULES
    assert env.action_masks().all()
    env.step(0)
    assert len(env.hidden_view().inbox) == 2 * N_RULES
