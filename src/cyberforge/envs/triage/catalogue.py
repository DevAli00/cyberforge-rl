"""The 12 alert types, in spec §4.3 order. Index in CATALOGUE = action number."""

from collections.abc import Mapping
from types import MappingProxyType

from cyberforge.envs.triage.types import MAX_STAGE, RuleSpec, Source

CATALOGUE: tuple[RuleSpec, ...] = (
    RuleSpec("phishing_link_clicked", 3, Source.EMAIL, 1, 0.10),
    RuleSpec("off_hours_login", 1, Source.IDENTITY, 1, 0.14),
    RuleSpec("new_admin_account", 2, Source.IDENTITY, 2, 0.02),
    RuleSpec("cloud_key_new_asn", 2, Source.CLOUD, 2, 0.02),
    RuleSpec("internal_port_scan", 4, Source.IDS, 3, 0.12),
    RuleSpec("mass_file_rename", 5, Source.EDR, 4, 0.01),
    RuleSpec("av_signature_hit", 5, Source.EDR, None, 0.16),
    RuleSpec("encoded_powershell", 4, Source.EDR, None, 0.06),
    RuleSpec("impossible_travel", 3, Source.IDENTITY, None, 0.10),
    RuleSpec("failed_login_burst", 3, Source.IDENTITY, None, 0.12),
    RuleSpec("dns_new_domain", 2, Source.IDS, None, 0.07),
    RuleSpec("usb_device_inserted", 1, Source.EDR, None, 0.08),
)

N_RULES: int = len(CATALOGUE)

# Attack stage -> indices of the alert types that stage can raise.
RULES_BY_STAGE: Mapping[int, tuple[int, ...]] = MappingProxyType(
    {
        stage: tuple(i for i, rule in enumerate(CATALOGUE) if rule.stage == stage)
        for stage in range(1, MAX_STAGE + 1)
    }
)
