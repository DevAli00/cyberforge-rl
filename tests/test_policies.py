"""Tests for the hand-written players of spec §6 (Random, SeverityFirst, AlwaysPhishing).

Written before the players exist: they fail until `cyberforge.agents.baselines` exists
with the classes `Random`, `SeverityFirst` and `AlwaysPhishing`.
Each player takes the catalogue in its constructor, so these tests can pass the provisional
`tests.fakes.CATALOGUE` and the real one can be swapped in later.
"""

import importlib
from typing import Any

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from numpy.typing import NDArray

from cyberforge.agents.base import Policy
from tests.fakes import CATALOGUE, N_IMPORTANCE, N_TYPES, OBS_SIZE, FakeTriageEnv


def index_of(rule_id: str) -> int:
    return next(i for i, r in enumerate(CATALOGUE) if r.rule_id == rule_id)


PHISHING = index_of("phishing_link_clicked")


def make_obs(waiting: NDArray[np.int64]) -> NDArray[np.float32]:
    """Observation from a (12, 3) table of waiting alerts, laid out as in spec §5."""
    obs = np.zeros(OBS_SIZE, dtype=np.float32)
    obs[: N_TYPES * N_IMPORTANCE] = waiting.reshape(-1) * 0.1
    return obs


def obs_and_mask(
    waiting: dict[str, tuple[int, int, int]],
) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
    """Inbox where only the given types have alerts, as counts per importance 1, 2, 3."""
    table = np.zeros((N_TYPES, N_IMPORTANCE), dtype=np.int64)
    for rule_id, counts in waiting.items():
        table[index_of(rule_id)] = counts
    return make_obs(table), table.sum(axis=1) > 0


@st.composite
def inboxes(draw: st.DrawFn) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
    """Random inbox: an observation and the mask that matches it (at least one True)."""
    flat = draw(
        st.lists(
            st.integers(0, 5),
            min_size=N_TYPES * N_IMPORTANCE,
            max_size=N_TYPES * N_IMPORTANCE,
        ).filter(any)
    )
    table = np.array(flat, dtype=np.int64).reshape(N_TYPES, N_IMPORTANCE)
    return make_obs(table), table.sum(axis=1) > 0


def baselines() -> Any:
    # Imported per test so that, until the players exist, only these tests fail
    # instead of the whole pytest run stopping at collection.
    return importlib.import_module("cyberforge.agents.baselines")


def players() -> list[Policy]:
    b = baselines()
    return [b.Random(), b.SeverityFirst(CATALOGUE), b.AlwaysPhishing(CATALOGUE)]


def top_importance(obs: NDArray[np.float32], action: int) -> int:
    """Index (0-2) of the most important machine with a waiting alert of this type."""
    row = obs[: N_TYPES * N_IMPORTANCE].reshape(N_TYPES, N_IMPORTANCE)[action]
    return int(np.flatnonzero(row > 0).max())


# (1) Every player only returns allowed actions.


@given(inbox=inboxes(), seed=st.integers(0, 2**32 - 1))
def test_players_only_pick_allowed_actions(
    inbox: tuple[NDArray[np.float32], NDArray[np.bool_]], seed: int
) -> None:
    obs, mask = inbox
    for player in players():
        action = player.act(obs, mask, np.random.default_rng(seed))
        assert isinstance(action, int)
        assert 0 <= action < N_TYPES
        assert mask[action], f"{player.name} picked masked action {action}"


def test_players_only_pick_allowed_actions_on_fake_env() -> None:
    env = FakeTriageEnv()
    rng = np.random.default_rng(0)
    for player in players():
        obs, _ = env.reset(seed=1)
        terminated = False
        while not terminated:
            mask = env.action_masks()
            action = player.act(obs, mask, rng)
            assert mask[action], f"{player.name} picked masked action {action}"
            obs, _, terminated, _, _ = env.step(action)


def test_players_have_distinct_names() -> None:
    names = [p.name for p in players()]
    assert all(names)
    assert len(set(names)) == len(names)


# (2) SeverityFirst: highest severity, then most important machine.


@given(inbox=inboxes(), seed=st.integers(0, 2**32 - 1))
def test_severity_first_picks_highest_severity_then_most_important_machine(
    inbox: tuple[NDArray[np.float32], NDArray[np.bool_]], seed: int
) -> None:
    obs, mask = inbox
    action = baselines().SeverityFirst(CATALOGUE).act(obs, mask, np.random.default_rng(seed))

    allowed = [int(i) for i in np.flatnonzero(mask)]
    best_severity = max(CATALOGUE[i].severity for i in allowed)
    assert CATALOGUE[action].severity == best_severity

    same_severity = [i for i in allowed if CATALOGUE[i].severity == best_severity]
    assert top_importance(obs, action) == max(top_importance(obs, i) for i in same_severity)


def test_severity_first_prefers_severity_over_machine_importance() -> None:
    obs, mask = obs_and_mask({"phishing_link_clicked": (0, 0, 3), "mass_file_rename": (1, 0, 0)})
    assert baselines().SeverityFirst(CATALOGUE).act(
        obs, mask, np.random.default_rng(0)
    ) == index_of("mass_file_rename")


def test_severity_first_breaks_severity_ties_by_machine_importance() -> None:
    # Both severity 4: the alert on an importance-3 machine wins over more alerts on importance 1.
    obs, mask = obs_and_mask({"av_signature_hit": (4, 0, 0), "encoded_powershell": (0, 0, 1)})
    assert baselines().SeverityFirst(CATALOGUE).act(
        obs, mask, np.random.default_rng(0)
    ) == index_of("encoded_powershell")


# (3) AlwaysPhishing: phishing if allowed, else any allowed action.


@given(inbox=inboxes(), seed=st.integers(0, 2**32 - 1))
def test_always_phishing_picks_phishing_when_allowed(
    inbox: tuple[NDArray[np.float32], NDArray[np.bool_]], seed: int
) -> None:
    obs, mask = inbox
    action = baselines().AlwaysPhishing(CATALOGUE).act(obs, mask, np.random.default_rng(seed))
    if mask[PHISHING]:
        assert action == PHISHING
    else:
        assert mask[action]


def test_always_phishing_falls_back_to_an_allowed_action() -> None:
    obs, mask = obs_and_mask({"off_hours_login": (1, 0, 0), "dns_new_domain": (0, 2, 0)})
    action = baselines().AlwaysPhishing(CATALOGUE).act(obs, mask, np.random.default_rng(0))
    assert action in {index_of("off_hours_login"), index_of("dns_new_domain")}
