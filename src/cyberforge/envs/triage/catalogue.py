"""The 12 alert types, in spec §4.3 order. Index in CATALOGUE = action number."""

from collections.abc import Mapping
from types import MappingProxyType

from cyberforge.envs.triage.types import MAX_STAGE, RuleSpec, Source

# Sources for these numbers: docs/research/ (W1 research notes) and the spec changelog.
# attack_weight: Mandiant M-Trends 2025, ransomware initial access (stage 1); even split otherwise.
CATALOGUE: tuple[RuleSpec, ...] = (
    # rule_id, severity, source, stage, noise_freq, attack_weight
    RuleSpec("phishing_link_clicked", 4, Source.EMAIL, 1, 0.10, 0.13),
    RuleSpec("off_hours_login", 1, Source.IDENTITY, 1, 0.14, 0.39),
    RuleSpec("new_admin_account", 2, Source.IDENTITY, 2, 0.02, 0.5),
    RuleSpec("cloud_key_new_asn", 3, Source.CLOUD, 2, 0.02, 0.5),
    RuleSpec("internal_port_scan", 2, Source.IDS, 3, 0.12, 1.0),
    RuleSpec("mass_file_rename", 5, Source.EDR, 4, 0.01, 1.0),
    RuleSpec("av_signature_hit", 4, Source.EDR, None, 0.16, 0.0),
    RuleSpec("encoded_powershell", 4, Source.EDR, None, 0.06, 0.0),
    RuleSpec("impossible_travel", 4, Source.IDENTITY, None, 0.10, 0.0),
    RuleSpec("failed_login_burst", 3, Source.IDENTITY, 1, 0.12, 0.48),
    RuleSpec("dns_new_domain", 2, Source.IDS, None, 0.07, 0.0),
    RuleSpec("usb_device_inserted", 1, Source.EDR, None, 0.08, 0.0),
)

N_RULES: int = len(CATALOGUE)

# Attack stage -> indices of the alert types that stage can raise.
RULES_BY_STAGE: Mapping[int, tuple[int, ...]] = MappingProxyType(
    {
        stage: tuple(i for i, rule in enumerate(CATALOGUE) if rule.stage == stage)
        for stage in range(1, MAX_STAGE + 1)
    }
)
