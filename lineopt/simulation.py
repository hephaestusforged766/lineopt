"""SimPy simulation of a serial production line with random task times.

Model:
- Station 1 always has raw material.
- Between stations there is a buffer with limited space. If the next buffer
  is full, the worker waits holding the unit ("blocking").
- Each worker repeatedly: takes a unit from the buffer before it, works on it,
  then puts it in the buffer after it.
"""
import math
import random

import simpy

from .analysis import Line


def _sample_time(rng: random.Random, mean: float, cv: float) -> float:
    """Lognormal time with the given mean and coefficient of variation (always > 0)."""
    if cv <= 0:
        return mean
    sigma2 = math.log(1 + cv * cv)
    mu = math.log(mean) - sigma2 / 2
    return rng.lognormvariate(mu, math.sqrt(sigma2))


def simulate_once(line: Line, sim_hours: float, warmup_hours: float, seed: int) -> dict:
    rng = random.Random(seed)
    env = simpy.Environment()
    n = len(line.stations)
    buffers = [simpy.Store(env, capacity=line.buffer_size) for _ in range(n - 1)]
    warmup = warmup_hours * 60.0
    end = warmup + sim_hours * 60.0

    busy = [0.0] * n
    blocked = [0.0] * n
    done_flow_times = []
    state = {"wip": 0, "next_id": 0}
    wip_samples = []
    buffer_samples = [[] for _ in range(n - 1)]

    def counted(t0, t1):
        """Part of [t0, t1] that is inside the measured period."""
        return max(0.0, min(t1, end) - max(t0, warmup))

    def worker(i):
        s = line.stations[i]
        while True:
            if i == 0:
                state["wip"] += 1
                item = env.now  # item = its start time
            else:
                item = yield buffers[i - 1].get()
            t0 = env.now
            yield env.timeout(_sample_time(rng, s.task_time, s.variation))
            busy[i] += counted(t0, env.now)
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
            for k, b in enumerate(buffers):
                buffer_samples[k].append(len(b.items))
            yield env.timeout(1.0)

    for i, s in enumerate(line.stations):
        for _ in range(s.workers):
            env.process(worker(i))
    env.process(sampler())
    env.run(until=end)

    measured = sim_hours * 60.0
    return {
        "output_per_hour": len(done_flow_times) / sim_hours,
        "avg_wip": sum(wip_samples) / len(wip_samples),
        "avg_flow_time": (sum(done_flow_times) / len(done_flow_times)) if done_flow_times else float("nan"),
        "utilization": {s.name: busy[i] / (s.workers * measured) for i, s in enumerate(line.stations)},
        "blocked_share": {s.name: blocked[i] / (s.workers * measured) for i, s in enumerate(line.stations)},
        "avg_buffer": [sum(b) / len(b) for b in buffer_samples],
    }


def simulate(line: Line, sim_hours: float = 40.0, warmup_hours: float = 2.0,
             replications: int = 5, seed: int = 1) -> dict:
    """Run several replications and average them (more runs = more reliable)."""
    runs = [simulate_once(line, sim_hours, warmup_hours, seed + r) for r in range(replications)]
    names = [s.name for s in line.stations]

    def avg(key):
        return sum(r[key] for r in runs) / len(runs)

    outs = [r["output_per_hour"] for r in runs]
    mean_out = sum(outs) / len(outs)
    sd = (sum((x - mean_out) ** 2 for x in outs) / (len(outs) - 1)) ** 0.5 if len(outs) > 1 else 0.0
    labor = sum(s.workers * s.wage_per_hour for s in line.stations)
    return {
        "output_per_hour": mean_out,
        "output_per_hour_sd": sd,
        "output_per_day": mean_out * line.hours_per_day,
        "avg_wip": avg("avg_wip"),
        "avg_flow_time": avg("avg_flow_time"),
        "labor_cost_per_unit": labor / mean_out if mean_out > 0 else float("inf"),
        "total_workers": sum(s.workers for s in line.stations),
        "utilization": {nm: sum(r["utilization"][nm] for r in runs) / len(runs) for nm in names},
        "blocked_share": {nm: sum(r["blocked_share"][nm] for r in runs) / len(runs) for nm in names},
        "avg_buffer": [sum(r["avg_buffer"][k] for r in runs) / len(runs) for k in range(len(names) - 1)],
    }
