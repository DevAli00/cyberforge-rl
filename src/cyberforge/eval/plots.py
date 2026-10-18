"""The three plots of spec §7, as PNG files."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes

# Reference categorical palette (fixed order) and recessive greys.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"


def _style(ax: Axes) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_learning_curves(
    curves: Sequence[Sequence[Mapping[str, float]]],
    baselines: Mapping[str, float],
    path: Path,
) -> None:
    """PPO average shift score vs shifts played (mean and min-max over seeds), baselines flat."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    n_points = min(len(c) for c in curves)
    if n_points:
        shifts = np.array([p["shifts"] for p in curves[0][:n_points]])
        scores = np.array([[p["mean_score"] for p in c[:n_points]] for c in curves])
        ax.fill_between(shifts, scores.min(axis=0), scores.max(axis=0), color=SERIES[0], alpha=0.2)
        ax.plot(shifts, scores.mean(axis=0), color=SERIES[0], linewidth=2, label="MaskablePPO")
    for i, (name, score) in enumerate(sorted(baselines.items())):
        color = SERIES[(i + 1) % len(SERIES)]
        ax.axhline(score, color=color, linewidth=1.5, linestyle="--", label=name)
    ax.set_xlabel("Shifts played")
    ax.set_ylabel("Average shift score")
    ax.set_title("PPO learning curve (mean, min-max over seeds)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_stopped_before_impact(players: Mapping[str, Mapping[str, Any]], path: Path) -> None:
    """Headline number per player, sorted, with 95% confidence intervals."""
    items = sorted(players.items(), key=lambda kv: kv[1]["stopped_before_impact"]["mean"])
    names = [name for name, _ in items]
    means = [s["stopped_before_impact"]["mean"] for _, s in items]
    cis = [s["stopped_before_impact"]["ci95"] for _, s in items]
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(names) + 1.5))
    ax.barh(names, means, xerr=cis, color=SERIES[0], height=0.6, capsize=3, ecolor=TEXT_SECONDARY)
    for y, (mean, ci) in enumerate(zip(means, cis, strict=True)):
        ax.text(mean + ci + 0.02, y, f"{mean:.2f}", va="center", color=TEXT_SECONDARY, fontsize=8)
    ax.set_xlabel("Attacks stopped before ransomware, per shift (95% CI)")
    ax.set_title("Attacks stopped before ransomware")
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_actions_heatmap(
    players: Mapping[str, Mapping[str, Any]],
    names: Sequence[str],
    type_labels: Sequence[str],
    path: Path,
) -> None:
    """Hero plot: share of shifts where each alert type is opened at each turn, side by side."""
    fig, axes = plt.subplots(1, len(names), figsize=(5 * len(names), 5), sharey=True)
    axes = np.atleast_1d(axes)
    image = None
    for ax, name in zip(axes, names, strict=True):
        counts = np.array(players[name]["actions_by_turn"], dtype=np.float64)  # (turn, type)
        share = counts / max(players[name]["n_shifts"], 1)
        image = ax.imshow(share.T, cmap="Blues", vmin=0, vmax=1, aspect="auto")
        ax.set_title(name)
        ax.set_xlabel("Turn")
        ax.set_xticks(range(counts.shape[0]), [str(t + 1) for t in range(counts.shape[0])])
        ax.tick_params(colors=TEXT_SECONDARY)
    axes[0].set_yticks(range(len(type_labels)), list(type_labels))
    if image is not None:
        fig.colorbar(image, ax=list(axes), label="Share of shifts")
    fig.suptitle("Which alert type each player opens at each turn")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
