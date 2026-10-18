import numpy as np
from gymnasium.utils.env_checker import check_env

from tests.fakes import CATALOGUE, FakeTriageEnv


def test_fake_env_passes_check_env() -> None:
    check_env(FakeTriageEnv(), skip_render_check=True)


def test_fake_env_obs_matches_mask_and_shift_lasts_10_turns() -> None:
    env = FakeTriageEnv()
    obs, info = env.reset(seed=0)
    assert set(info) == {
        "attacks_total",
        "contained_early",
        "contained_stage3",
        "reached_impact",
        "false_alarms",
    }
    for turn in range(1, 11):
        mask = env.action_masks()
        assert mask.shape == (12,)
        assert mask.dtype == np.bool_
        assert mask.any()
        waiting = obs[:36].reshape(12, 3).sum(axis=1)
        assert np.all((waiting > 0) == mask)
        assert np.all(obs[36:48][~mask] == 0)
        action = int(np.flatnonzero(mask)[0])
        obs, _, terminated, truncated, _ = env.step(action)
        assert terminated == (turn == 10)
        assert truncated is False
        assert obs[48] == np.float32(turn / 10)


def test_fake_env_is_seeded() -> None:
    a, b = FakeTriageEnv(), FakeTriageEnv()
    obs_a, _ = a.reset(seed=42)
    obs_b, _ = b.reset(seed=42)
    np.testing.assert_array_equal(obs_a, obs_b)
    np.testing.assert_array_equal(a.action_masks(), b.action_masks())
    assert a.hidden_view() == b.hidden_view()


def test_catalogue_has_12_rules_with_noise_summing_to_1() -> None:
    assert len(CATALOGUE) == 12
    assert len({r.rule_id for r in CATALOGUE}) == 12
    assert abs(sum(r.noise_freq for r in CATALOGUE) - 1.0) < 1e-9
