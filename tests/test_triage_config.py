"""Spec §4: game settings."""

import dataclasses

import pytest

from cyberforge.envs.triage.config import NoiseCount, TriageConfig


def test_defaults_match_spec() -> None:
    config = TriageConfig()
    assert config.n_turns == 10
    assert config.noise_per_turn == 9
    assert config.attack_count_choices == (2, 3, 4)
    assert config.max_start_turn == 5
    assert config.p_advance == 0.6
    assert config.attack_importance_probs == (0.2, 0.3, 0.5)
    assert config.noise_importance_probs == (0.5, 0.35, 0.15)
    assert config.reward_contain_early == 1.0
    assert config.reward_contain_stage3 == 0.5
    assert config.reward_open_impact == 0.2
    assert config.penalty_impact == -5.0
    assert config.penalty_running_at_end == -1.0
    assert config.count_scale == 0.1


def test_config_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        TriageConfig().n_turns = 5  # type: ignore[misc]


def test_config_can_be_overridden() -> None:
    assert TriageConfig(p_advance=0.5).p_advance == 0.5


@pytest.mark.parametrize(
    "overrides",
    [
        {"n_turns": 0},
        {"noise_per_turn": -1},
        {"attack_count_choices": ()},
        {"attack_count_choices": (0, 2)},
        {"max_start_turn": -1},
        {"max_start_turn": 10},  # must start before the shift ends
        {"p_advance": -0.1},
        {"p_advance": 1.1},
        {"attack_importance_probs": (0.5, 0.5)},
        {"attack_importance_probs": (0.5, 0.5, 0.5)},
        {"noise_importance_probs": (1.2, -0.1, -0.1)},
        {"count_scale": 0.0},
        {"penalty_impact": 1.0},
        {"penalty_running_at_end": 1.0},
        {"reward_contain_early": -1.0},
    ],
)
def test_config_rejects_bad_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"TriageConfig"):
        TriageConfig(**overrides)  # type: ignore[arg-type]


# --- noise_count: how many false alarms arrive per turn ------------------------------------


def test_noise_count_defaults_to_fixed() -> None:
    config = TriageConfig()
    assert config.noise_count is NoiseCount.FIXED
    assert config.max_noise_per_turn == 9


@pytest.mark.parametrize(
    ("noise_count", "max_noise"),
    [
        (NoiseCount.FIXED, 9),
        (NoiseCount.BINOMIAL, 18),
        (NoiseCount.POISSON, 18),
        (NoiseCount.UNIFORM, 12),
    ],
)
def test_max_noise_per_turn(noise_count: NoiseCount, max_noise: int) -> None:
    assert TriageConfig(noise_count=noise_count).max_noise_per_turn == max_noise


def test_noise_count_accepts_plain_strings() -> None:
    assert TriageConfig(noise_count="poisson").noise_count is NoiseCount.POISSON  # type: ignore[arg-type]


def test_noise_count_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match=r"TriageConfig"):
        TriageConfig(noise_count="gaussian")  # type: ignore[arg-type]


def test_uniform_needs_an_average_of_at_least_the_spread() -> None:
    with pytest.raises(ValueError, match=r"TriageConfig"):
        TriageConfig(noise_count=NoiseCount.UNIFORM, noise_per_turn=2)
