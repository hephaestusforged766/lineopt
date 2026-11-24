"""Line balancing: assign tasks to stations so each station's work fits the takt time.

Method: Ranked Positional Weight (RPW, Helgeson & Birnie).
- Positional weight of a task = its time + the time of every task that must come after it.
- Take tasks from highest to lowest weight; put each in the current station if
  (a) all tasks it depends on are already placed, and (b) it still fits in the takt time.
- When nothing more fits, open a new station.
"""
import math

import pandas as pd


def parse_tasks(df: pd.DataFrame) -> list:
    """df columns: task, time_min, predecessors (e.g. 'A;B' or blank)."""
    d = df.copy()
    d.columns = [c.strip().lower() for c in d.columns]
    need = {"task", "time_min", "predecessors"}
    if not need <= set(d.columns):
        raise ValueError("The task table needs columns: task, time_min, predecessors.")
    tasks = []
    for r in d.itertuples():
        if pd.isna(r.task) or str(r.task).strip() == "":
            continue
        preds = [] if pd.isna(r.predecessors) else [p.strip() for p in str(r.predecessors).replace(",", ";").split(";") if p.strip()]
        tasks.append({"task": str(r.task).strip(), "time": float(r.time_min), "preds": preds,
                      "description": str(getattr(r, "description", "") or "")})
    return tasks


def check_tasks(tasks: list) -> list:
    problems = []
    names = [t["task"] for t in tasks]
    known = set(names)
    if len(known) != len(names):
        problems.append("Task IDs must be unique.")
    for t in tasks:
        if not t["time"] > 0:
            problems.append(f"Task {t['task']}: time must be more than 0.")
        for p in t["preds"]:
            if p not in known:
                problems.append(f"Task {t['task']}: unknown predecessor '{p}'.")
    if not problems and _has_cycle(tasks):
        problems.append("The predecessors form a loop (A needs B and B needs A).")
    return problems


def _has_cycle(tasks):
    preds = {t["task"]: t["preds"] for t in tasks}
    state = {}

    def visit(n):
        if state.get(n) == 1:
            return True
        if state.get(n) == 2:
            return False
        state[n] = 1
        if any(visit(p) for p in preds[n]):
            return True
        state[n] = 2
        return False

    return any(visit(n) for n in preds)


def positional_weights(tasks: list) -> dict:
    succ = {t["task"]: set() for t in tasks}
    for t in tasks:
        for p in t["preds"]:
            succ[p].add(t["task"])
    time = {t["task"]: t["time"] for t in tasks}

    def all_followers(n, seen=None):
        seen = set() if seen is None else seen
        for s in succ[n]:
            if s not in seen:
                seen.add(s)
                all_followers(s, seen)
        return seen

    return {n: time[n] + sum(time[f] for f in all_followers(n)) for n in time}


def balance(tasks: list, takt: float) -> dict:
    """Return stations (list of task lists) and efficiency numbers."""
    pw = positional_weights(tasks)
    order = sorted(tasks, key=lambda t: -pw[t["task"]])
    placed, stations = set(), []
    remaining = list(order)
    while remaining:
        load, current = 0.0, []
        progress = True
        while progress:
            progress = False
            for t in remaining:
                ready = all(p in placed for p in t["preds"])
                # A task longer than takt gets its own station (needs parallel workers)
                fits = load + t["time"] <= takt + 1e-9 or (not current and t["time"] > takt)
                if ready and fits:
                    current.append(t)
                    placed.add(t["task"])
                    load += t["time"]
                    remaining.remove(t)
                    progress = True
                    break
            if current and current[-1]["time"] > takt:
                break
        stations.append(current)

    total = sum(t["time"] for t in tasks)
    rows = []
    for k, st in enumerate(stations, 1):
        load = sum(t["time"] for t in st)
        workers = max(1, math.ceil(load / takt - 1e-9))
        rows.append({"station": f"Station {k}", "tasks": " + ".join(t["task"] for t in st),
                     "time_min": load, "workers": workers,
                     "idle_min": workers * takt - load})
    n_workers = sum(r["workers"] for r in rows)
    return {
        "stations": rows,
        "theoretical_min_stations": math.ceil(total / takt - 1e-9),
        "work_content": total,
        "efficiency": total / (n_workers * takt),
        "balance_delay": 1 - total / (n_workers * takt),
        "positional_weight": pw,
    }
