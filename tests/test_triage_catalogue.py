"""Spec §4.3: the 12 alert types."""

import math

import pytest

from cyberforge.envs.triage.catalogue import CATALOGUE, N_RULES, RULES_BY_STAGE
from cyberforge.envs.triage.types import Source

# Copy of the spec §4.3 table. If this test fails, the catalogue and the spec disagree.
SPEC_TABLE = [
    # rule_id, severity, source, stage, noise_freq, attack_weight
    ("phishing_link_clicked", 4, Source.EMAIL, 1, 0.10, 0.13),
    ("off_hours_login", 1, Source.IDENTITY, 1, 0.14, 0.39),
    ("new_admin_account", 2, Source.IDENTITY, 2, 0.02, 0.5),
    ("cloud_key_new_asn", 3, Source.CLOUD, 2, 0.02, 0.5),
    ("internal_port_scan", 2, Source.IDS, 3, 0.12, 1.0),
    ("mass_file_rename", 5, Source.EDR, 4, 0.01, 1.0),
    ("av_signature_hit", 4, Source.EDR, None, 0.16, 0.0),
    ("encoded_powershell", 4, Source.EDR, None, 0.06, 0.0),
    ("impossible_travel", 4, Source.IDENTITY, None, 0.10, 0.0),
    ("failed_login_burst", 3, Source.IDENTITY, 1, 0.12, 0.48),
    ("dns_new_domain", 2, Source.IDS, None, 0.07, 0.0),
    ("usb_device_inserted", 1, Source.EDR, None, 0.08, 0.0),
]


def test_has_12_rules() -> None:
    assert N_RULES == 12
    assert len(CATALOGUE) == N_RULES


@pytest.mark.parametrize(("index", "row"), list(enumerate(SPEC_TABLE)))
def test_rule_matches_spec_row(index: int, row: tuple[object, ...]) -> None:
    rule = CATALOGUE[index]
    fields = (rule.rule_id, rule.severity, rule.source, rule.stage, rule.noise_freq)
    assert (*fields, rule.attack_weight) == row


def test_rule_ids_are_unique() -> None:
    assert len({rule.rule_id for rule in CATALOGUE}) == N_RULES


def test_noise_freq_sums_to_one() -> None:
    assert math.isclose(sum(rule.noise_freq for rule in CATALOGUE), 1.0)


def test_rules_by_stage() -> None:
    assert dict(RULES_BY_STAGE) == {1: (0, 1, 9), 2: (2, 3), 3: (4,), 4: (5,)}


def test_rules_by_stage_is_read_only() -> None:
    with pytest.raises(TypeError):
        RULES_BY_STAGE[1] = (0,)  # type: ignore[index]


def test_early_types_noisier_than_ransomware() -> None:
    """Design rule: early alert types stay noisy, late ones stay reliable."""
    late = max(CATALOGUE[i].noise_freq for i in RULES_BY_STAGE[4])
    early = min(CATALOGUE[i].noise_freq for i in RULES_BY_STAGE[1])
    assert late < early


@pytest.mark.parametrize("stage", range(1, 5))
def test_attack_weights_of_a_stage_sum_to_one(stage: int) -> None:
    assert math.isclose(sum(CATALOGUE[i].attack_weight for i in RULES_BY_STAGE[stage]), 1.0)


def test_mass_file_rename_is_the_only_severity_5() -> None:
    """The article's story: sort-by-severity chases the alert that comes too late."""
    assert [rule.rule_id for rule in CATALOGUE if rule.severity == 5] == ["mass_file_rename"]
