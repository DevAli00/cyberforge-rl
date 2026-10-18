import numpy as np
import pytest

from cyberforge.agents.bandit import LearnedBandit
from cyberforge.agents.oracle import Oracle, opened_alert
from cyberforge.agents.smart_analyst import SmartAnalyst
from tests.fakes import (
    CATALOGUE,
    N_TYPES,
    OBS_SIZE,
    FakeAlert,
    FakeAttack,
    FakeHiddenView,
    FakeTriageEnv,
)

OBS = np.zeros(OBS_SIZE, dtype=np.float32)


def index_of(rule_id: str) -> int:
    return next(i for i, r in enumerate(CATALOGUE) if r.rule_id == rule_id)


def mask_of(*rule_ids: str) -> np.ndarray:
    mask = np.zeros(N_TYPES, dtype=np.bool_)
    mask[[index_of(r) for r in rule_ids]] = True
    return mask


# Smart analyst: stage 2 > stage 3 > stage 1 > bandit.


@pytest.mark.parametrize(
    ("allowed", "expected"),
    [
        (("phishing_link_clicked", "internal_port_scan", "new_admin_account"), "new_admin_account"),
        (("phishing_link_clicked", "internal_port_scan", "av_signature_hit"), "internal_port_scan"),
        (
            ("phishing_link_clicked", "av_signature_hit", "mass_file_rename"),
            "phishing_link_clicked",
        ),
    ],
)
def test_smart_analyst_follows_stage_priority(allowed: tuple[str, ...], expected: str) -> None:
    analyst = SmartAnalyst(CATALOGUE, LearnedBandit(epsilon=0.0))
    assert analyst.act(OBS, mask_of(*allowed), np.random.default_rng(0)) == index_of(expected)


def test_smart_analyst_falls_back_to_the_bandit_and_teaches_it() -> None:
    analyst = SmartAnalyst(CATALOGUE, LearnedBandit(epsilon=0.0))
    analyst.update(index_of("dns_new_domain"), 1.0)
    assert analyst.bandit.counts.sum() == 1
    mask = mask_of("av_signature_hit", "dns_new_domain", "mass_file_rename")
    # mass_file_rename is stage 4: not in the priority list, so the bandit decides.
    mask[index_of("mass_file_rename")] = False
    assert analyst.act(OBS, mask, np.random.default_rng(0)) == index_of("dns_new_domain")


def test_smart_analyst_lets_the_bandit_choose_within_a_stage() -> None:
    analyst = SmartAnalyst(CATALOGUE, LearnedBandit(epsilon=0.0))
    analyst.update(index_of("cloud_key_new_asn"), 1.0)
    mask = mask_of("new_admin_account", "cloud_key_new_asn")
    assert analyst.act(OBS, mask, np.random.default_rng(0)) == index_of("cloud_key_new_asn")


# Oracle: stops the running attack closest to ransomware, using Ali's HiddenView shape.


class StubEnv:
    def __init__(self, attacks: list[FakeAttack], inbox: list[FakeAlert]) -> None:
        self.view = FakeHiddenView(0, tuple(attacks), tuple(inbox))

    def hidden_view(self) -> FakeHiddenView:
        return self.view


def alert(
    alert_id: int, rule_id: str, importance: int = 1, attack_id: int | None = None
) -> FakeAlert:
    return FakeAlert(alert_id, index_of(rule_id), importance, turn=0, attack_id=attack_id)


def oracle_pick(attacks: list[FakeAttack], inbox: list[FakeAlert]) -> int:
    mask = np.zeros(N_TYPES, dtype=np.bool_)
    for a in inbox:
        mask[a.rule_index] = True
    return Oracle(StubEnv(attacks, inbox)).act(OBS, mask, np.random.default_rng(0))


def test_oracle_goes_after_the_attack_closest_to_ransomware() -> None:
    attacks = [
        FakeAttack(0, 1, "active"),
        FakeAttack(1, 3, "active"),
        FakeAttack(2, 2, "contained"),
    ]
    inbox = [
        alert(0, "phishing_link_clicked", attack_id=0),
        alert(1, "internal_port_scan", attack_id=1),
        alert(2, "new_admin_account", attack_id=2),  # contained: ignored
    ]
    assert oracle_pick(attacks, inbox) == index_of("internal_port_scan")


def test_oracle_puts_attacks_already_at_ransomware_last() -> None:
    attacks = [FakeAttack(0, 4, "active"), FakeAttack(1, 1, "active")]
    inbox = [alert(0, "mass_file_rename", attack_id=0), alert(1, "off_hours_login", attack_id=1)]
    assert oracle_pick(attacks, inbox) == index_of("off_hours_login")


def test_oracle_skips_a_type_where_a_false_alarm_would_be_opened_first() -> None:
    # Stage-3 attack on an importance-1 machine, but a false alarm of the same type sits on an
    # importance-3 machine: the game would open the false alarm, so the oracle takes stage 1.
    attacks = [FakeAttack(0, 3, "active"), FakeAttack(1, 1, "active")]
    inbox = [
        alert(0, "internal_port_scan", importance=1, attack_id=0),
        alert(1, "internal_port_scan", importance=3),
        alert(2, "phishing_link_clicked", importance=2, attack_id=1),
    ]
    assert oracle_pick(attacks, inbox) == index_of("phishing_link_clicked")


def test_opened_alert_follows_spec_order() -> None:
    inbox = [
        FakeAlert(0, 4, importance=2, turn=1),
        FakeAlert(1, 4, importance=2, turn=3),
        FakeAlert(2, 4, importance=2, turn=3),
        FakeAlert(3, 4, importance=1, turn=5),
    ]
    # Most important machine, then most recent, then lowest alert_id.
    assert opened_alert(inbox, 4).alert_id == 1


def test_oracle_falls_back_to_an_allowed_type_without_attack_alerts() -> None:
    attacks = [FakeAttack(0, 2, "active")]
    inbox = [alert(0, "usb_device_inserted"), alert(1, "dns_new_domain")]
    assert oracle_pick(attacks, inbox) in {
        index_of("usb_device_inserted"),
        index_of("dns_new_domain"),
    }


def test_oracle_plays_a_full_shift_on_fake_env() -> None:
    env = FakeTriageEnv()
    oracle = Oracle(env)
    rng = np.random.default_rng(0)
    obs, _ = env.reset(seed=5)
    terminated = False
    while not terminated:
        mask = env.action_masks()
        action = oracle.act(obs, mask, rng)
        assert mask[action]
        obs, _, terminated, _, _ = env.step(action)
