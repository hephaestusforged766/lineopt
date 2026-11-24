"""SimPy simulation of a serial production line.

Model:
- Station 1 always has raw material.
- Between stations there is a buffer with limited space. If the next buffer
  is full, the worker waits holding the unit ("blocking").
- Each worker repeatedly: takes a unit, works on it, then passes it on.
- Random task times (lognormal), random breakdowns (exponential time between
  failures, counted in working minutes) and random scrap (defects).
- Each station uses its own random-number stream, so two scenarios with the
  same seed see the same "luck" (common random numbers). This makes the
  comparison between scenarios fairer.
"""
import math
import random

import simpy

from .analysis import Line
from .stats import mean_ci, paired_diff_ci


def _sample_time(rng: random.Random, mean: float, cv: float) -> float:
    """Lognormal time with the given mean and coefficient of variation (always > 0)."""
    if cv <= 0:
        return mean
    sigma2 = math.log(1 + cv * cv)
    mu = math.log(mean) - sigma2 / 2
    return rng.lognormvariate(mu, math.sqrt(sigma2))


def simulate_once(line: Line, sim_hours: float, warmup_hours: float, seed: int) -> dict:
    env = simpy.Environment()
    n = len(line.stations)
    buffers = [simpy.Store(env, capacity=line.buffer_size) for _ in range(n - 1)]
    warmup = warmup_hours * 60.0
    end = warmup + sim_hours * 60.0

    busy = [0.0] * n
    blocked = [0.0] * n
    down = [0.0] * n
    scrapped = [0] * n
    done_flow_times = []
    state = {"wip": 0}
    wip_samples = []

    def counted(t0, t1):
        """Part of [t0, t1] that is inside the measured period."""
        return max(0.0, min(t1, end) - max(t0, warmup))

    def worker(i, w):
        s = line.stations[i]
        # Separate streams per station/worker and per purpose -> common random numbers
        r_time = random.Random(f"{seed}-t-{i}-{w}")
        r_fail = random.Random(f"{seed}-f-{i}-{w}")
        r_defect = random.Random(f"{seed}-d-{i}-{w}")
        breaks = s.mtbf > 0 and s.mttr > 0
        to_failure = r_fail.expovariate(1 / s.mtbf) if breaks else math.inf
        while True:
            if i == 0:
                state["wip"] += 1
                item = env.now  # item = its start time
            else:
                item = yield buffers[i - 1].get()
            work_left = _sample_time(r_time, s.task_time, s.variation)
            while work_left > 0:
                if work_left < to_failure:
                    t0 = env.now
                    yield env.timeout(work_left)
                    busy[i] += counted(t0, env.now)
                    to_failure -= work_left
                    work_left = 0
                else:  # breaks down part-way through this unit
                    t0 = env.now
                    yield env.timeout(to_failure)
                    busy[i] += counted(t0, env.now)
                    work_left -= to_failure
                    t1 = env.now
                    yield env.timeout(r_fail.expovariate(1 / s.mttr))
                    down[i] += counted(t1, env.now)
                    to_failure = r_fail.expovariate(1 / s.mtbf)
            if s.defect_rate > 0 and r_defect.random() < s.defect_rate:
                state["wip"] -= 1
                if env.now >= warmup:
                    scrapped[i] += 1
                continue
            if i == n - 1:
                state["wip"] -= 1
                if env.now >= warmup:
                    done_flow_times.append(env.now - item)
            else:
                t1 = env.now
                yield buffers[i].put(item)
                blocked[i] += counted(t1, env.now)

    def sampler():
        yield env.timeout(warmup)
        while True:
            wip_samples.append(state["wip"])
            yield env.timeout(1.0)

    for i, s in enumerate(line.stations):
        for w in range(s.workers):
            env.process(worker(i, w))
    env.process(sampler())
    env.run(until=end)

    measured = sim_hours * 60.0
    names = [s.name for s in line.stations]
    cap = {nm: line.stations[i].workers * measured for i, nm in enumerate(names)}
    return {
        "output_per_hour": len(done_flow_times) / sim_hours,
        "avg_wip": sum(wip_samples) / len(wip_samples),
        "avg_flow_time": (sum(done_flow_times) / len(done_flow_times)) if done_flow_times else float("nan"),
        "scrap_per_hour": sum(scrapped) / sim_hours,
        "utilization": {nm: busy[i] / cap[nm] for i, nm in enumerate(names)},
        "blocked_share": {nm: blocked[i] / cap[nm] for i, nm in enumerate(names)},
        "down_share": {nm: down[i] / cap[nm] for i, nm in enumerate(names)},
    }


def simulate(line: Line, sim_hours: float = 40.0, warmup_hours: float = 2.0,
             replications: int = 5, seed: int = 1) -> dict:
    """Run several replications and average them, with 95% confidence intervals."""
    runs = [simulate_once(line, sim_hours, warmup_hours, seed + r) for r in range(replications)]
    names = [s.name for s in line.stations]
    outs = [r["output_per_hour"] for r in runs]
    m, half = mean_ci(outs)
    wip_m, wip_half = mean_ci([r["avg_wip"] for r in runs])
    labor = sum(s.workers * s.wage_per_hour for s in line.stations)

    def avg_map(key):
        return {nm: sum(r[key][nm] for r in runs) / len(runs) for nm in names}

    return {
        "runs_output": outs,
        "output_per_hour": m,
        "output_ci": half,                       # +- half-width of 95% confidence interval
        "output_per_day": m * line.hours_per_day,
        "avg_wip": wip_m,
        "wip_ci": wip_half,
        "avg_flow_time": sum(r["avg_flow_time"] for r in runs) / len(runs),
        "scrap_per_hour": sum(r["scrap_per_hour"] for r in runs) / len(runs),
        "labor_cost_per_unit": labor / m if m > 0 else float("inf"),
        "labor_cost_per_hour": labor,
        "total_workers": sum(s.workers for s in line.stations),
        "utilization": avg_map("utilization"),
        "blocked_share": avg_map("blocked_share"),
        "down_share": avg_map("down_share"),
    }


def compare(base: dict, other: dict) -> tuple:
    """Paired 95% CI for (other - base) output/hour. Same seeds -> paired by run."""
    return paired_diff_ci(base["runs_output"], other["runs_output"])
