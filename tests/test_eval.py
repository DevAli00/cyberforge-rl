import json

import numpy as np
import pytest

from cyberforge.agents.baselines import Random
from cyberforge.eval.evaluate import evaluate, write_outputs
from cyberforge.eval.metrics import mean_ci95, summarize
from cyberforge.eval.runner import (
    TEST_SEED_START,
    ShiftRecord,
    evaluation_seeds,
    play_shifts,
    real_env_factory,
)
from cyberforge.training.train_ppo import train, train_and_save
from tests.fakes import CATALOGUE, N_TYPES, FakeTriageEnv

TINY_PPO = {"n_steps": 50, "batch_size": 50, "n_epochs": 1}


def test_evaluation_seeds_are_the_same_new_shifts_for_everyone() -> None:
    assert evaluation_seeds(3) == [1_000_000, 1_000_001, 1_000_002]
    assert TEST_SEED_START == 1_000_000


def test_mean_ci95() -> None:
    assert mean_ci95([2.0, 2.0, 2.0]) == {"mean": 2.0, "ci95": 0.0}
    result = mean_ci95([0.0, 1.0] * 50)
    assert result["mean"] == 0.5
    assert result["ci95"] == pytest.approx(1.96 * np.std([0, 1] * 50, ddof=1) / 10, abs=1e-6)
    assert mean_ci95([3.0]) == {"mean": 3.0, "ci95": 0.0}


def test_play_shifts_records_ten_turns_and_final_info() -> None:
    records = play_shifts(FakeTriageEnv(), Random(), evaluation_seeds(5))
    assert [r.seed for r in records] == evaluation_seeds(5)
    for r in records:
        assert len(r.actions) == 10
        assert r.false_alarms == 10  # the fake counts every opened alert as a false alarm
        assert 2 <= r.attacks_total <= 4


def test_play_shifts_is_deterministic() -> None:
    a = play_shifts(FakeTriageEnv(), Random(), evaluation_seeds(5))
    b = play_shifts(FakeTriageEnv(), Random(), evaluation_seeds(5))
    assert a == b


def test_summarize_counts_actions_by_turn_and_headline() -> None:
    records = [
        ShiftRecord(0, 1.0, 3, 1, 1, 0, 8, actions=[0] * 10),
        ShiftRecord(1, -5.0, 2, 0, 0, 1, 10, actions=[1] * 10),
    ]
    summary = summarize(records, N_TYPES)
    assert summary["stopped_before_impact"]["mean"] == 1.0
    assert summary["reached_impact"]["mean"] == 0.5
    assert summary["score"]["mean"] == -2.0
    assert summary["actions_by_turn"][0][:2] == [1, 1]
    assert sum(map(sum, summary["actions_by_turn"])) == 20


def test_train_logs_the_average_shift_score() -> None:
    model, curve = train(FakeTriageEnv, seed=0, n_shifts=20, log_every=10, ppo_kwargs=TINY_PPO)
    assert [p["shifts"] for p in curve] == [10, 20]
    assert all(p["mean_score"] == 0.0 for p in curve)  # the fake always gives 0 points
    assert model.num_timesteps >= 200


def test_end_to_end_evaluation_writes_results_and_plots(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cyberforge.training.train_ppo.train",
        lambda make_env, seed, n_shifts: train(make_env, seed, n_shifts, 10, TINY_PPO),
    )
    models, experiments = tmp_path / "models", tmp_path / "experiments"
    model_path = train_and_save(FakeTriageEnv, 0, 20, models, experiments)
    assert model_path.exists()

    results = evaluate(FakeTriageEnv, CATALOGUE, [model_path], n_shifts=20)
    names = set(results["players"])
    assert names == {
        "random",
        "severity_first",
        "always_phishing",
        "learned_bandit",
        "smart_analyst",
        "oracle",
        "maskable_ppo_maskable_ppo_seed0",
        "maskable_ppo",
    }
    assert results["alert_types"] == [r.rule_id for r in CATALOGUE]

    write_outputs(results, experiments)
    text = (experiments / "results.json").read_text()
    assert json.loads(text) == json.loads(json.dumps(results))
    for png in ["stopped_before_impact.png", "learning_curve.png", "hero_actions.png"]:
        assert (experiments / png).stat().st_size > 0

    # Same inputs, same file: results.json is deterministic.
    write_outputs(evaluate(FakeTriageEnv, CATALOGUE, [model_path], n_shifts=20), experiments)
    assert (experiments / "results.json").read_text() == text


def test_real_env_factory_loads_ali_triage_env() -> None:
    from cyberforge.envs.triage.env import TriageEnv

    assert real_env_factory() is TriageEnv


def test_scripts_explain_when_the_real_env_is_missing(monkeypatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "cyberforge.envs.triage.env", None)
    with pytest.raises(SystemExit, match="not merged yet"):
        real_env_factory()
