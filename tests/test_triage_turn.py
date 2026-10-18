"""Spec §4.4-4.5: one turn of the real game.

Two kinds of tests:
- Wiring: Ali's hand-written rules are swapped for recording stand-ins, to check that the env
  calls them at the right moment with the right inputs. Green before Ali writes the rules.
- Whole game: the real rules. Red until Ali writes rules.py.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

import cyberforge.envs.triage.env as env_module
from cyberforge.envs.triage.catalogue import RULES_BY_STAGE
from cyberforge.envs.triage.config import NoiseCount, TriageConfig
from cyberforge.envs.triage.env import TriageEnv
from cyberforge.envs.triage.rules import opened_alert
from cyberforge.envs.triage.types import Alert, Attack, AttackStatus, HiddenView

# --- helpers --------------------------------------------------------------------------------


def _allowed(env: TriageEnv) -> list[int]:
    return [int(a) for a in np.flatnonzero(env.action_masks())]


def _attack_action(env: TriageEnv) -> int | None:
    """A type whose opened alert belongs to an attack, if any."""
    view = env.hidden_view()
    for action in _allowed(env):
        if opened_alert(view.inbox, action).attack_id is not None:
            return action
    return None


def _false_alarm_action(env: TriageEnv) -> int | None:
    view = env.hidden_view()
    for action in _allowed(env):
        if opened_alert(view.inbox, action).is_false_alarm:
            return action
    return None


def _env_with_attack_alert(config: TriageConfig | None = None) -> tuple[TriageEnv, int]:
    """A freshly reset env where some type opens an attack alert on the first step."""
    for seed in range(500):
        env = TriageEnv(config)
        env.reset(seed=seed)
        action = _attack_action(env)
        if action is not None:
            return env, action
    raise AssertionError("no seed opens an attack alert on turn 1")


@dataclass
class Recorder:
    """Stand-ins for Ali's rules that record how the env calls them."""

    contain_calls: list[tuple[Alert, tuple[Attack, ...], tuple[Alert, ...]]] = field(
        default_factory=list
    )
    points_calls: list[int] = field(default_factory=list)
    impact_calls: list[tuple[Attack, Attack]] = field(default_factory=list)
    end_calls: list[tuple[Attack, ...]] = field(default_factory=list)

    def contain(
        self, opened: Alert, attacks: tuple[Attack, ...], inbox: tuple[Alert, ...]
    ) -> tuple[tuple[Attack, ...], tuple[Alert, ...]]:
        self.contain_calls.append((opened, attacks, inbox))
        return attacks, inbox

    def containment_points(self, stage: int, config: TriageConfig) -> float:
        self.points_calls.append(stage)
        return 100.0

    def impact_points(self, before: Attack, after: Attack, config: TriageConfig) -> float:
        self.impact_calls.append((before, after))
        return -10.0 if after.stage > before.stage else 0.0

    def end_of_shift_points(self, attacks: tuple[Attack, ...], config: TriageConfig) -> float:
        self.end_calls.append(attacks)
        return -1000.0


@pytest.fixture
def rec(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    for name in ("contain", "containment_points", "impact_points", "end_of_shift_points"):
        monkeypatch.setattr(env_module, name, getattr(recorder, name))
    return recorder


# --- wiring (green before Ali writes the rules) ---------------------------------------------


def test_step_opens_the_alert_picked_by_opened_alert(rec: Recorder) -> None:
    env = TriageEnv()
    env.reset(seed=0)
    before = env.hidden_view()
    action = _allowed(env)[0]
    expected = opened_alert(before.inbox, action)
    env.step(action)
    opened, attacks, rest = rec.contain_calls[0]
    assert opened == expected
    assert attacks == before.attacks
    assert rest == tuple(a for a in before.inbox if a != expected)  # removed before contain()
    assert expected not in env.hidden_view().inbox


def test_false_alarm_scores_nothing_and_is_counted(rec: Recorder) -> None:
    config = TriageConfig(p_advance=0.0)
    env = TriageEnv(config)
    env.reset(seed=0)
    action = _false_alarm_action(env)
    assert action is not None
    _, reward, _, _, info = env.step(action)
    assert rec.points_calls == []
    assert reward == 0.0
    assert info["false_alarms"] == 1


def test_attack_alert_scores_its_current_stage(rec: Recorder) -> None:
    env, action = _env_with_attack_alert(TriageConfig(p_advance=0.0))
    view = env.hidden_view()
    owner = opened_alert(view.inbox, action).attack_id
    stage = next(a.stage for a in view.attacks if a.attack_id == owner)
    _, reward, _, _, info = env.step(action)
    assert rec.points_calls == [stage]
    assert reward == 100.0
    assert info["false_alarms"] == 0
    assert info["contained_early"] == (1 if stage <= 2 else 0)


def test_every_attack_is_checked_for_impact_each_turn(rec: Recorder) -> None:
    env = TriageEnv(TriageConfig(p_advance=1.0))
    env.reset(seed=0)
    n_attacks = len(env.hidden_view().attacks)
    env.step(_allowed(env)[0])
    assert len(rec.impact_calls) == n_attacks
    for before, after in rec.impact_calls:
        if before.status is AttackStatus.ACTIVE and before.stage < 4:
            assert after.stage == before.stage + 1  # p_advance = 1
        else:
            assert after == before


def test_advanced_attacks_raise_an_alert_that_arrives_this_turn(rec: Recorder) -> None:
    env = TriageEnv(TriageConfig(p_advance=1.0, max_start_turn=0))  # all start on turn 1
    env.reset(seed=0)
    env.step(_allowed(env)[0])
    view = env.hidden_view()
    for attack in view.attacks:
        newest = [a for a in view.alerts_of(attack.attack_id) if a.turn == 1]
        assert len(newest) == 1
        assert newest[0].rule_index in RULES_BY_STAGE[attack.stage]


def test_reaching_ransomware_is_counted(rec: Recorder) -> None:
    env = TriageEnv(TriageConfig(p_advance=1.0, max_start_turn=0))
    env.reset(seed=0)
    infos = [env.step(_allowed(env)[0])[4] for _ in range(3)]  # stage 1 -> 4 in 3 turns
    assert infos[-1]["reached_impact"] == len(env.hidden_view().attacks)


def test_end_of_shift_is_scored_once_on_the_last_step(rec: Recorder) -> None:
    env = TriageEnv(TriageConfig(n_turns=3, max_start_turn=2, p_advance=0.0))
    env.reset(seed=0)
    rewards = []
    for _ in range(3):
        rewards.append(env.step(_false_alarm_action(env) or _allowed(env)[0])[1])
    assert len(rec.end_calls) == 1
    assert rec.end_calls[0] == env.hidden_view().attacks
    assert rewards[-1] <= -1000.0
    assert all(r > -1000.0 for r in rewards[:-1])


def test_arrivals_are_shuffled_before_numbering(rec: Recorder) -> None:
    """Attack alerts must not always get the lowest or highest ids of their turn (tie fairness)."""
    positions = set()
    for seed in range(60):
        env = TriageEnv(TriageConfig(max_start_turn=0, noise_count=NoiseCount.FIXED))
        env.reset(seed=seed)
        inbox = env.hidden_view().inbox
        positions |= {i for i, a in enumerate(inbox) if not a.is_false_alarm}
    assert min(positions) == 0
    assert max(positions) == env.config.noise_per_turn + max(env.config.attack_count_choices) - 1


# --- whole game (red until Ali writes rules.py) ---------------------------------------------


def _play(seed: int, config: TriageConfig | None = None) -> tuple[TriageEnv, float, dict[str, Any]]:
    env = TriageEnv(config)
    env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    score, info, terminated = 0.0, {}, False
    while not terminated:
        _, reward, terminated, _, info = env.step(int(rng.choice(_allowed(env))))
        score += reward
    return env, score, info


def _expected_score(view: HiddenView, config: TriageConfig) -> float:
    """Spec §4.5 worked out from the final truth."""
    points = {1: config.reward_contain_early, 2: config.reward_contain_early}
    points |= {3: config.reward_contain_stage3, 4: config.reward_open_impact}
    score = 0.0
    for attack in view.attacks:
        if attack.status is AttackStatus.CONTAINED:
            score += points[attack.stage]
        if attack.stage == 4:
            score += config.penalty_impact
        if attack.status is AttackStatus.ACTIVE and attack.stage < 4:
            score += config.penalty_running_at_end
    return score


@pytest.mark.parametrize("seed", range(30))
def test_shift_score_matches_the_rules(seed: int) -> None:
    env, score, _ = _play(seed)
    assert score == pytest.approx(_expected_score(env.hidden_view(), env.config))


@pytest.mark.parametrize("seed", range(30))
def test_info_matches_the_final_truth(seed: int) -> None:
    env, _, info = _play(seed)
    attacks = env.hidden_view().attacks
    contained = [a for a in attacks if a.status is AttackStatus.CONTAINED]
    assert info["attacks_total"] == len(attacks)
    assert info["contained_early"] == sum(a.stage <= 2 for a in contained)
    assert info["contained_stage3"] == sum(a.stage == 3 for a in contained)
    assert info["reached_impact"] == sum(a.stage == 4 for a in attacks)
    assert info["false_alarms"] == env.config.n_turns - len(contained)


def test_contained_attack_leaves_the_inbox_and_stops_moving() -> None:
    env, action = _env_with_attack_alert(TriageConfig(p_advance=1.0))
    owner = opened_alert(env.hidden_view().inbox, action).attack_id
    env.step(action)
    for _ in range(3):
        view = env.hidden_view()
        attack = next(a for a in view.attacks if a.attack_id == owner)
        assert attack.status is AttackStatus.CONTAINED
        assert view.alerts_of(owner) == ()
        env.step(_allowed(env)[0])


def test_attack_reaching_ransomware_costs_minus_5() -> None:
    config = TriageConfig(p_advance=1.0, max_start_turn=0, attack_count_choices=(1,))
    env = TriageEnv(config)
    env.reset(seed=0)
    rewards = []
    for _ in range(3):
        action = _false_alarm_action(env)
        assert action is not None
        rewards.append(env.step(action)[1])
    assert rewards == pytest.approx([0.0, 0.0, -5.0])


def test_same_seed_same_score() -> None:
    assert _play(7)[1] == _play(7)[1]
