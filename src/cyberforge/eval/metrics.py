"""Turns shift records into the numbers of spec §7, with 95% confidence intervals."""

from collections.abc import Sequence
from typing import Any

import numpy as np

from cyberforge.eval.runner import ShiftRecord

N_TURNS = 10
DECIMALS = 6  # rounded so results.json is byte-for-byte deterministic


def mean_ci95(values: Sequence[float]) -> dict[str, float]:
    """Mean and half-width of the 95% confidence interval (normal approximation)."""
    x = np.asarray(values, dtype=np.float64)
    half_width = 1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0
    return {"mean": round(float(x.mean()), DECIMALS), "ci95": round(float(half_width), DECIMALS)}


def actions_by_turn(records: Sequence[ShiftRecord], n_types: int) -> list[list[int]]:
    """How many times each alert type was opened at each turn: a (turn, type) count table."""
    counts = np.zeros((N_TURNS, n_types), dtype=np.int64)
    for record in records:
        for turn, action in enumerate(record.actions):
            counts[turn, action] += 1
    return counts.tolist()


def summarize(records: Sequence[ShiftRecord], n_types: int) -> dict[str, Any]:
    """Every §7 metric for one player."""
    return {
        "stopped_before_impact": mean_ci95([r.stopped_before_impact for r in records]),
        "reached_impact": mean_ci95([r.reached_impact for r in records]),
        "score": mean_ci95([r.score for r in records]),
        "false_alarms": mean_ci95([r.false_alarms for r in records]),
        "stopped_by_stage": {
            "stage_1_2": mean_ci95([r.contained_early for r in records]),
            "stage_3": mean_ci95([r.contained_stage3 for r in records]),
        },
        "attacks_total": mean_ci95([r.attacks_total for r in records]),
        "actions_by_turn": actions_by_turn(records, n_types),
        "n_shifts": len(records),
    }
