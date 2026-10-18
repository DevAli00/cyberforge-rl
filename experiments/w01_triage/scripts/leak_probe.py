"""Probe: does trained PPO rely on 'exactly 9 false alarms per turn'?

Plays the same 1,000 test shifts twice: the normal game, and a patched game where the number of
false alarms per turn is Poisson(9). Only this script is patched; the repo code is unchanged.
"""

import dataclasses
import glob
import sys

import numpy as np

import cyberforge.envs.triage.env as env_module
from cyberforge.agents.bandit import LearnedBandit
from cyberforge.agents.oracle import Oracle
from cyberforge.agents.ppo import PPOPolicy
from cyberforge.agents.smart_analyst import SmartAnalyst
from cyberforge.envs.triage.catalogue import CATALOGUE
from cyberforge.envs.triage.config import TriageConfig
from cyberforge.envs.triage.env import TriageEnv
from cyberforge.envs.triage.types import Alert
from cyberforge.eval.runner import evaluation_seeds, play_shifts

N_SHIFTS = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000
ORIGINAL = env_module.draw_false_alarms


def varying_false_alarms(
    rng: np.random.Generator, config: TriageConfig, turn: int, first_id: int
) -> tuple[Alert, ...]:
    n = int(rng.poisson(config.noise_per_turn))
    return ORIGINAL(rng, dataclasses.replace(config, noise_per_turn=n), turn, first_id)


def players(env: TriageEnv) -> list[object]:
    ppo = [
        PPOPolicy.load(p, name=f"ppo_{p[-9:-4]}")
        for p in sorted(glob.glob("models/w01_triage/*.zip"))
    ]
    return [*ppo, LearnedBandit(len(CATALOGUE)), SmartAnalyst(CATALOGUE), Oracle(env)]


def run(label: str) -> dict[str, tuple[float, float]]:
    seeds = evaluation_seeds(N_SHIFTS)
    out = {}
    for index in range(len(players(TriageEnv()))):
        env = TriageEnv()
        player = players(env)[index]
        records = play_shifts(env, player, seeds)
        out[player.name] = (
            float(np.mean([r.stopped_before_impact for r in records])),
            float(np.mean([r.score for r in records])),
        )
    return out


def leak_availability() -> float:
    """Share of turns where an attack alert arrives ("more than 9" would give it away)."""
    hits = total = 0
    for seed in evaluation_seeds(200):
        env = TriageEnv()
        env.reset(seed=seed)
        done = False
        while not done:
            mask = env.action_masks()
            _, _, done, _, _ = env.step(int(np.flatnonzero(mask)[0]))
            arrived = env._arrived
            hits += any(a.attack_id is not None for a in arrived)
            total += 1
    return hits / total


fixed = run("fixed 9")
env_module.draw_false_alarms = varying_false_alarms
varying = run("Poisson(9)")
env_module.draw_false_alarms = ORIGINAL

print(f"turns where an attack alert arrives: {leak_availability():.0%}\n")
HEADER = (
    "player",
    "stopped fixed",
    "stopped vary",
    "change",
    "score fixed",
    "score vary",
    "change",
)
print("{:16}{:>15}{:>15}{:>9}{:>13}{:>13}{:>9}".format(*HEADER))
for name in fixed:
    (s0, sc0), (s1, sc1) = fixed[name], varying[name]
    row = (name, s0, s1, s1 - s0, sc0, sc1, sc1 - sc0)
    print("{:16}{:15.2f}{:15.2f}{:+9.2f}{:13.2f}{:13.2f}{:+9.2f}".format(*row))
