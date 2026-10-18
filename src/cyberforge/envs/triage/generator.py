"""Random content of a shift (spec §4.1-4.3): false alarms and attacks.

Pure functions: randomness only from the `rng` passed in (the env's own generator), and they
return new frozen objects instead of changing their inputs.
"""

from collections.abc import Sequence
from dataclasses import replace

import numpy as np

from cyberforge.envs.triage.catalogue import CATALOGUE, N_RULES, RULES_BY_STAGE
from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.types import MAX_STAGE, N_IMPORTANCE, Alert, Attack, AttackStatus

_IMPORTANCE_LEVELS = np.arange(1, N_IMPORTANCE + 1)
_NOISE_PROBS = np.array([rule.noise_freq for rule in CATALOGUE])


def draw_attacks(rng: np.random.Generator, config: TriageConfig) -> tuple[Attack, ...]:
    """2-4 hidden attacks, each with a start turn and a target machine. All still pending."""
    n_attacks = int(rng.choice(config.attack_count_choices))
    starts = rng.integers(0, config.max_start_turn + 1, size=n_attacks)
    importances = rng.choice(_IMPORTANCE_LEVELS, size=n_attacks, p=config.attack_importance_probs)
    return tuple(
        Attack(attack_id=i, start_turn=int(start), importance=int(importance))
        for i, (start, importance) in enumerate(zip(starts, importances, strict=True))
    )


def draw_false_alarms(
    rng: np.random.Generator, config: TriageConfig, turn: int, first_id: int
) -> tuple[Alert, ...]:
    """`noise_per_turn` independent false alarms, type from noise_freq, machine from
    noise_importance_probs. Ids are first_id, first_id + 1, ..."""
    n_alarms = config.noise_per_turn
    types = rng.choice(N_RULES, size=n_alarms, p=_NOISE_PROBS)
    importances = rng.choice(_IMPORTANCE_LEVELS, size=n_alarms, p=config.noise_importance_probs)
    return tuple(
        Alert(alert_id=first_id + i, rule_index=int(rule), importance=int(imp), turn=turn)
        for i, (rule, imp) in enumerate(zip(types, importances, strict=True))
    )


def start_attack(
    rng: np.random.Generator, attack: Attack, turn: int, alert_id: int
) -> tuple[Attack, Alert]:
    """A pending attack enters stage 1 and raises its first alert."""
    if attack.status is not AttackStatus.PENDING:
        raise ValueError(f"attack {attack.attack_id} is not pending (status {attack.status})")
    started = Attack(
        attack_id=attack.attack_id,
        start_turn=attack.start_turn,
        importance=attack.importance,
        stage=1,
        status=AttackStatus.ACTIVE,
    )
    return started, _stage_alert(rng, started, turn, alert_id)


def try_advance(
    rng: np.random.Generator, attack: Attack, config: TriageConfig, turn: int, alert_id: int
) -> tuple[Attack, Alert | None]:
    """An active attack below ransomware moves up one stage with p_advance, raising one alert of
    its new stage. Otherwise it is returned unchanged with no alert (and no dice are rolled)."""
    if attack.status is not AttackStatus.ACTIVE or attack.stage >= MAX_STAGE:
        return attack, None
    if rng.random() >= config.p_advance:
        return attack, None
    moved = Attack(
        attack_id=attack.attack_id,
        start_turn=attack.start_turn,
        importance=attack.importance,
        stage=attack.stage + 1,
        status=AttackStatus.ACTIVE,
    )
    return moved, _stage_alert(rng, moved, turn, alert_id)


def _stage_alert(rng: np.random.Generator, attack: Attack, turn: int, alert_id: int) -> Alert:
    """One alert of the attack's current stage, on its target machine. The type is picked among
    the stage's types by their attack_weight."""
    candidates = RULES_BY_STAGE[attack.stage]
    weights = [CATALOGUE[i].attack_weight for i in candidates]
    rule_index = int(rng.choice(candidates, p=weights))
    return Alert(
        alert_id=alert_id,
        rule_index=rule_index,
        importance=attack.importance,
        turn=turn,
        attack_id=attack.attack_id,
    )


def shuffle_arrivals(rng: np.random.Generator, arrivals: Sequence[Alert]) -> tuple[Alert, ...]:
    """Mix a turn's arrivals in random order, then give them their ids again in that order, so
    the lowest-id tie-break (§4.4 step 1) favours neither false alarms nor attack alerts."""
    ids = sorted(alert.alert_id for alert in arrivals)
    order = rng.permutation(len(arrivals))
    return tuple(
        replace(arrivals[int(i)], alert_id=new_id) for i, new_id in zip(order, ids, strict=True)
    )
