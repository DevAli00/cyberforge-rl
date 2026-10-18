"""Spec §4: game settings."""

import dataclasses

import pytest

from cyberforge.envs.triage.config import TriageConfig


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
