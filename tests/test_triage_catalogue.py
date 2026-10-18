"""Spec §4.3: the 12 alert types."""

import math

import pytest

from cyberforge.envs.triage.catalogue import CATALOGUE, N_RULES, RULES_BY_STAGE
from cyberforge.envs.triage.types import Source

# Copy of the spec §4.3 table. If this test fails, the catalogue and the spec disagree.
SPEC_TABLE = [
    ("phishing_link_clicked", 3, Source.EMAIL, 1, 0.10),
    ("off_hours_login", 1, Source.IDENTITY, 1, 0.14),
    ("new_admin_account", 2, Source.IDENTITY, 2, 0.02),
    ("cloud_key_new_asn", 2, Source.CLOUD, 2, 0.02),
    ("internal_port_scan", 4, Source.IDS, 3, 0.12),
    ("mass_file_rename", 5, Source.EDR, 4, 0.01),
    ("av_signature_hit", 5, Source.EDR, None, 0.16),
    ("encoded_powershell", 4, Source.EDR, None, 0.06),
    ("impossible_travel", 3, Source.IDENTITY, None, 0.10),
    ("failed_login_burst", 3, Source.IDENTITY, None, 0.12),
    ("dns_new_domain", 2, Source.IDS, None, 0.07),
    ("usb_device_inserted", 1, Source.EDR, None, 0.08),
]


def test_has_12_rules() -> None:
    assert N_RULES == 12
    assert len(CATALOGUE) == N_RULES


@pytest.mark.parametrize(("index", "row"), list(enumerate(SPEC_TABLE)))
def test_rule_matches_spec_row(index: int, row: tuple[object, ...]) -> None:
    rule = CATALOGUE[index]
    assert (rule.rule_id, rule.severity, rule.source, rule.stage, rule.noise_freq) == row


def test_rule_ids_are_unique() -> None:
    assert len({rule.rule_id for rule in CATALOGUE}) == N_RULES


def test_noise_freq_sums_to_one() -> None:
    assert math.isclose(sum(rule.noise_freq for rule in CATALOGUE), 1.0)


def test_rules_by_stage() -> None:
    assert dict(RULES_BY_STAGE) == {1: (0, 1), 2: (2, 3), 3: (4,), 4: (5,)}


def test_rules_by_stage_is_read_only() -> None:
    with pytest.raises(TypeError):
        RULES_BY_STAGE[1] = (0,)  # type: ignore[index]


def test_early_types_noisier_than_ransomware() -> None:
    """Design rule: early alert types stay noisy, late ones stay reliable."""
    late = max(CATALOGUE[i].noise_freq for i in RULES_BY_STAGE[4])
    early = min(CATALOGUE[i].noise_freq for i in RULES_BY_STAGE[1])
    assert late < early
