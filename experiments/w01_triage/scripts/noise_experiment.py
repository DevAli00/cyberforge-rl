"""Train MaskablePPO on each varying noise_count game, then evaluate every player on it.

Uses Rayane's train_and_save and evaluate unchanged; only the env factory differs.
Outputs under OUT/<noise_count>/ (models, learning curves, results.json, plots).
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from cyberforge.envs.triage.catalogue import CATALOGUE
from cyberforge.envs.triage.config import NoiseCount, TriageConfig
from cyberforge.envs.triage.env import TriageEnv
from cyberforge.eval.evaluate import evaluate, write_outputs
from cyberforge.training.train_ppo import train_and_save

OUT = Path(sys.argv[1])
SHIFTS = 30_000
SEEDS = (0, 1, 2)
VARIANTS = (NoiseCount.BINOMIAL, NoiseCount.POISSON, NoiseCount.UNIFORM)


def make_env_factory(noise_count: NoiseCount) -> partial[TriageEnv]:
    return partial(TriageEnv, TriageConfig(noise_count=noise_count))


def main() -> None:
    jobs = [(v, seed) for v in VARIANTS for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [
            pool.submit(
                train_and_save, make_env_factory(v), seed, SHIFTS, OUT / v / "models", OUT / v
            )
            for v, seed in jobs
        ]
        for future in futures:
            print("saved", future.result(), flush=True)

    for v in VARIANTS:
        models = sorted((OUT / v / "models").glob("*.zip"))
        results = evaluate(make_env_factory(v), CATALOGUE, models, 1_000)
        write_outputs(results, OUT / v)
        print("evaluated", v, flush=True)

    summary = {
        v.value: json.loads((OUT / v / "results.json").read_text())["players"] for v in VARIANTS
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
