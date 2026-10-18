"""Spec §5: the TriageEnv interface (skeleton, placeholder logic until #6 and #9)."""

import warnings
from collections import Counter

import numpy as np
import pytest
from gymnasium import spaces
from gymnasium.utils.env_checker import check_env

from cyberforge.envs.triage.catalogue import N_RULES
from cyberforge.envs.triage.config import NoiseCount, TriageConfig
from cyberforge.envs.triage.env import TriageEnv
from cyberforge.envs.triage.observation import observation_high
from cyberforge.envs.triage.types import AttackStatus, HiddenView, InvalidActionError

INFO_KEYS = {
    "attacks_total",
    "contained_early",
    "contained_stage3",
    "reached_impact",
    "false_alarms",
}


def _first_allowed(env: TriageEnv) -> int:
    return int(np.flatnonzero(env.action_masks())[0])


class _MaskRespectingEnv(TriageEnv):
    """Test-only: check_env presses random buttons and ignores the mask, so a masked press
    becomes the first allowed type. The real game keeps raising (spec §5). A subclass, not a
    gymnasium Wrapper, because check_env warns on wrapped envs."""

    def step(self, action: int | np.integer) -> tuple[np.ndarray, float, bool, bool, dict]:
        mask = self.action_masks()
        if 0 <= action < N_RULES and not mask[action]:
            action = int(np.flatnonzero(mask)[0])
        return super().step(action)


def test_passes_check_env() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_env(_MaskRespectingEnv(), skip_render_check=True)


def _grey_out(env: TriageEnv, rule_index: int) -> None:
    """Test-only: remove every waiting alert of one type, so its button is masked."""
    env._inbox = tuple(a for a in env._inbox if a.rule_index != rule_index)
    assert not env.action_masks()[rule_index]


def test_check_env_adapter_swaps_a_masked_press() -> None:
    env = _MaskRespectingEnv()
    env.reset(seed=0)
    _grey_out(env, 0)
    env.step(0)  # swapped for an allowed type instead of raising


def test_real_step_refuses_a_masked_press() -> None:
    env = TriageEnv()
    env.reset(seed=0)
    _grey_out(env, 0)
    before = env.hidden_view()
    with pytest.raises(InvalidActionError):
        env.step(0)
    assert env.hidden_view() == before


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


def _attack_alerts(view: HiddenView) -> Counter[int]:
    return Counter(a.attack_id for a in view.inbox if a.attack_id is not None)


@pytest.mark.parametrize("seed", range(10))
def test_reset_starts_attacks_due_on_turn_1(seed: int) -> None:
    env = TriageEnv(TriageConfig(noise_count=NoiseCount.FIXED))  # exact false-alarm count
    env.reset(seed=seed)
    view = env.hidden_view()
    assert len(view.attacks) in env.config.attack_count_choices
    for attack in view.attacks:
        if attack.start_turn == 0:
            assert (attack.status, attack.stage) == (AttackStatus.ACTIVE, 1)
        else:
            assert (attack.status, attack.stage) == (AttackStatus.PENDING, 0)
    started = {a.attack_id for a in view.attacks if a.start_turn == 0}
    assert _attack_alerts(view) == Counter(dict.fromkeys(started, 1))
    false_alarms = [a for a in view.inbox if a.is_false_alarm]
    assert len(false_alarms) == env.config.noise_per_turn


@pytest.mark.parametrize("seed", range(10))
def test_each_attack_starts_on_its_turn(seed: int) -> None:
    env = TriageEnv()
    env.reset(seed=seed)
    terminated = False
    while not terminated:
        _, _, terminated, _, _ = env.step(_first_allowed(env))
        view = env.hidden_view()
        for attack in view.attacks:
            assert (attack.status is AttackStatus.PENDING) == (attack.start_turn > view.turn)


def test_arrivals_carry_the_turn_they_arrive_on() -> None:
    env = TriageEnv()
    env.reset(seed=0)
    env.step(_first_allowed(env))
    newest = env.hidden_view().inbox[-env.config.noise_per_turn :]
    assert {a.turn for a in newest} == {1}


def test_alert_ids_are_unique_and_increasing() -> None:
    env = TriageEnv()
    env.reset(seed=0)
    for _ in range(5):
        env.step(_first_allowed(env))
    ids = [a.alert_id for a in env.hidden_view().inbox]
    assert ids == sorted(set(ids))


def test_some_types_are_really_masked() -> None:
    """Real arrivals leave rare types empty, so the mask is not always all true."""
    masks = []
    for seed in range(20):
        env = TriageEnv()
        env.reset(seed=seed)
        masks.append(env.action_masks().all())
    assert not all(masks)


@pytest.mark.parametrize("noise_count", list(NoiseCount))
def test_observations_stay_inside_the_space(noise_count: NoiseCount) -> None:
    env = TriageEnv(TriageConfig(noise_count=noise_count))
    rng = np.random.default_rng(0)
    for seed in range(20):
        obs, _ = env.reset(seed=seed)
        assert env.observation_space.contains(obs)
        terminated = False
        while not terminated:
            obs, _, terminated, _, _ = env.step(int(rng.choice(np.flatnonzero(env.action_masks()))))
            assert env.observation_space.contains(obs)


def test_varying_noise_count_changes_arrivals_between_turns() -> None:
    env = TriageEnv(TriageConfig(noise_count=NoiseCount.BINOMIAL))
    env.reset(seed=0)
    counts = set()
    for _ in range(10):
        env.step(_first_allowed(env))
        counts.add(
            sum(
                a.is_false_alarm and a.turn == env.hidden_view().turn
                for a in env.hidden_view().inbox
            )
        )
    assert len(counts) > 1


@pytest.mark.parametrize("seed", [9741, 10078, 21607])
def test_shift_never_starts_with_an_empty_inbox(seed: int) -> None:
    """These Poisson seeds drew 0 false alarms on turn 1 with no attack starting (E5 crash)."""
    env = TriageEnv(TriageConfig(noise_count=NoiseCount.POISSON))
    env.reset(seed=seed)
    assert env.action_masks().any()
