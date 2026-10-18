"""The turn rules of the triage game (spec §4.4-4.5). Pure functions.

`opened_alert` is wiring. The four functions below it are the containment and reward logic,
reserved for Ali to write by hand (spec §8). TEMPORARY: the current versions were written by
Claude at Ali's request (2026-10-18) so the game could be tested end to end; Ali will rewrite
them by hand. Tests in tests/test_triage_rules.py and tests/test_triage_turn.py say what each
must do.
"""

from collections.abc import Sequence
from dataclasses import replace

from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.types import MAX_STAGE, Alert, Attack, AttackStatus


def opened_alert(inbox: Sequence[Alert], rule_index: int) -> Alert:
    """The alert the game opens for this type (§4.4 step 1): most important machine first, then
    most recent, then lowest alert_id. Shared with the oracle so both always agree."""
    of_type = [alert for alert in inbox if alert.rule_index == rule_index]
    if not of_type:
        raise ValueError(f"no alert of type {rule_index} is waiting")
    return max(of_type, key=lambda alert: (alert.importance, alert.turn, -alert.alert_id))


# --- Reserved for Ali (TEMPORARY versions written by Claude, to be rewritten by hand) ----------


def contain(
    opened: Alert, attacks: tuple[Attack, ...], inbox: tuple[Alert, ...]
) -> tuple[tuple[Attack, ...], tuple[Alert, ...]]:
    """§4.4 step 2. `inbox` no longer holds `opened` (the env removed it).

    False alarm: return `attacks` and `inbox` unchanged.
    Attack alert: that attack becomes CONTAINED (same stage), and all its other alerts leave the
    inbox (other alerts keep their order). Return new tuples; never change the inputs.
    """
    if opened.attack_id is None:
        return attacks, inbox
    stopped = tuple(
        replace(a, status=AttackStatus.CONTAINED) if a.attack_id == opened.attack_id else a
        for a in attacks
    )
    remaining = tuple(alert for alert in inbox if alert.attack_id != opened.attack_id)
    return stopped, remaining


def containment_points(stage: int, config: TriageConfig) -> float:
    """§4.5: points for stopping an attack at its current `stage`: stage 1-2 ->
    reward_contain_early, 3 -> reward_contain_stage3, 4 -> reward_open_impact.
    Any other stage: raise ValueError."""
    if stage in (1, 2):
        return config.reward_contain_early
    if stage == 3:
        return config.reward_contain_stage3
    if stage == MAX_STAGE:
        return config.reward_open_impact
    raise ValueError(f"an attack alert can only come from stage 1-{MAX_STAGE}, got stage {stage}")


def impact_points(before: Attack, after: Attack, config: TriageConfig) -> float:
    """§4.5: penalty_impact if the attack reached stage 4 this turn (before < 4, after == 4),
    else 0. Called for every attack, every turn, after the advance roll."""
    if before.stage < MAX_STAGE and after.stage == MAX_STAGE:
        return config.penalty_impact
    return 0.0


def end_of_shift_points(attacks: tuple[Attack, ...], config: TriageConfig) -> float:
    """§4.5: penalty_running_at_end for each attack still ACTIVE below stage 4 when the shift
    ends. Stage-4 attacks already paid penalty_impact; contained ones are done."""
    running = [a for a in attacks if a.status is AttackStatus.ACTIVE and a.stage < MAX_STAGE]
    return config.penalty_running_at_end * len(running)
