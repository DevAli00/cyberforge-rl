import numpy as np
import pytest

from cyberforge.agents.bandit import LearnedBandit
from cyberforge.agents.oracle import HiddenView, Oracle
from cyberforge.agents.smart_analyst import SmartAnalyst
from tests.fakes import CATALOGUE, N_TYPES, OBS_SIZE, FakeTriageEnv

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


# Oracle: the running attack closest to ransomware.


class StubEnv:
    def __init__(self, view: HiddenView) -> None:
        self.view = view

    def hidden_view(self) -> HiddenView:
        return self.view


def attack(attack_id: int, stage: int, types: list[str], stopped: bool = False) -> dict:
    return {
        "attack_id": attack_id,
        "stage": stage,
        "stopped": stopped,
        "waiting_alert_types": [index_of(t) for t in types],
    }


def test_oracle_goes_after_the_attack_closest_to_ransomware() -> None:
    view = {
        "attacks": [
            attack(0, 1, ["phishing_link_clicked"]),
            attack(1, 3, ["internal_port_scan"]),
            attack(2, 4, ["mass_file_rename"], stopped=True),
        ]
    }
    oracle = Oracle(StubEnv(view))  # type: ignore[arg-type]
    mask = mask_of("phishing_link_clicked", "internal_port_scan", "mass_file_rename")
    assert oracle.act(OBS, mask, np.random.default_rng(0)) == index_of("internal_port_scan")


def test_oracle_ignores_masked_alerts_and_falls_back_to_allowed() -> None:
    view = {"attacks": [attack(0, 3, ["internal_port_scan"])]}
    oracle = Oracle(StubEnv(view))  # type: ignore[arg-type]
    mask = mask_of("usb_device_inserted")
    assert oracle.act(OBS, mask, np.random.default_rng(0)) == index_of("usb_device_inserted")


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
