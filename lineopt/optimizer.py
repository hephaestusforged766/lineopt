"""Generate improvement scenarios, simulate each, and rank them by a goal."""
from dataclasses import replace

from .analysis import Line, analyze
from .simulation import simulate

GOALS = {
    "Most output per hour": ("output_per_hour", True),
    "Least work-in-progress (WIP)": ("avg_wip", False),
    "Lowest labor cost per unit": ("labor_cost_per_unit", False),
    "Fewest workers (must meet demand)": ("total_workers", False),
}


def _bottleneck_index(line: Line) -> int:
    return max(range(len(line.stations)), key=lambda i: line.stations[i].cycle_time)


def scenarios(line: Line) -> list:
    """Return [(name, explanation, new_line)]. Baseline first."""
    out = [("Current line", "No change.", line.copy())]
    b = _bottleneck_index(line)
    bname = line.stations[b].name

    # 1. Add one worker at the bottleneck
    l1 = line.copy()
    l1.stations[b].workers += 1
    out.append((f"Add worker at {bname}", f"Hire 1 more worker for the slowest station ({bname}).", l1))

    # 2. Move a worker from the least busy station (with 2+ workers) to the bottleneck
    donors = [i for i, s in enumerate(line.stations) if i != b and s.workers >= 2]
    if donors:
        d = min(donors, key=lambda i: line.stations[i].task_time / (line.stations[i].workers - 1))
        l2 = line.copy()
        l2.stations[d].workers -= 1
        l2.stations[b].workers += 1
        out.append((f"Move worker {line.stations[d].name} -> {bname}",
                    "Same number of workers, no hiring cost.", l2))

    # 3. Bigger buffers (more space for units between stations)
    l3 = line.copy(buffer_size=line.buffer_size * 2)
    out.append((f"Double buffer space ({line.buffer_size} -> {line.buffer_size * 2})",
                "More space between stations so variation causes less blocking. Raises WIP.", l3))

    # 4. Standard work at the bottleneck: halve its time variation
    if line.stations[b].variation > 0:
        l4 = line.copy()
        l4.stations[b].variation = round(line.stations[b].variation / 2, 3)
        out.append((f"Standard work at {bname}",
                    "Training/jigs make the bottleneck's time more consistent (variation halved).", l4))

    # 5. Fewest workers that still meet demand (formula-based, greedy)
    if line.demand_per_day > 0:
        l5 = line.copy(stations=[replace(s, workers=1) for s in line.stations])
        while not analyze(l5)["meets_demand"] and sum(s.workers for s in l5.stations) < 200:
            i = _bottleneck_index(l5)
            l5.stations[i].workers += 1
        # Add a small safety margin: randomness usually lowers real output by a few %
        if analyze(l5)["output_per_day"] < line.demand_per_day * 1.05:
            l5.stations[_bottleneck_index(l5)].workers += 1
        staffing = ", ".join(f"{s.name}={s.workers}" for s in l5.stations)
        out.append(("Minimum staffing for demand",
                    f"Fewest workers whose capacity meets demand +5% margin: {staffing}.", l5))
    return out


def evaluate(line: Line, goal: str, sim_hours=40.0, replications=5, seed=1) -> list:
    """Simulate every scenario and return rows sorted best-first for the goal."""
    key, higher_better = GOALS[goal]
    rows = []
    base = None
    for name, why, ln in scenarios(line):
        r = simulate(ln, sim_hours=sim_hours, replications=replications, seed=seed)
        meets = (r["output_per_day"] >= line.demand_per_day) if line.demand_per_day > 0 else None
        row = {
            "Scenario": name,
            "What changes": why,
            "Output/hour": r["output_per_hour"],
            "Output/day": r["output_per_day"],
            "Meets demand": meets,
            "Avg WIP (units)": r["avg_wip"],
            "Avg flow time (min)": r["avg_flow_time"],
            "Workers": r["total_workers"],
            "Labor cost/unit": r["labor_cost_per_unit"],
            "_line": ln,
            "_sim": r,
        }
        rows.append(row)
        if base is None:
            base = row
    for row in rows:
        row["Output change %"] = 100 * (row["Output/hour"] / base["Output/hour"] - 1)
        row["WIP change %"] = 100 * (row["Avg WIP (units)"] / base["Avg WIP (units)"] - 1)
        row["Cost/unit change %"] = 100 * (row["Labor cost/unit"] / base["Labor cost/unit"] - 1) \
            if base["Labor cost/unit"] > 0 else 0.0

    col = {"output_per_hour": "Output/hour", "avg_wip": "Avg WIP (units)",
           "labor_cost_per_unit": "Labor cost/unit", "total_workers": "Workers"}[key]

    def sort_key(row):
        # Scenarios that miss demand go last when there is a demand target
        penalty = 0 if row["Meets demand"] in (True, None) else 1
        v = row[col]
        return (penalty, -v if higher_better else v)

    return sorted(rows, key=sort_key)
