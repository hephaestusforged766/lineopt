"""Simulation-optimization: build candidate improvements, simulate each, rank by a goal.

Step 1 (formulas): for every total number of workers N, find the BEST way to
spread N workers over the stations. Greedy rule: always give the next worker to
the station that limits the line most. For this kind of problem ("maximize the
slowest station's capacity") the greedy rule gives the optimal allocation.

Step 2 (combinations): combine the best staffing with other levers -
bigger buffers and standard work (less time variation) at the bottleneck.

Step 3 (simulation): simulate every candidate with the SAME random numbers,
attach 95% confidence intervals, and rank by the user's goal and limits.
"""
from .analysis import Line, analyze, start_rates
from .simulation import compare, simulate

GOALS = {
    "Most output per hour": ("Output/hour", True),
    "Lowest labor cost per unit": ("Labor cost/unit", False),
    "Least work-in-progress (WIP)": ("Avg WIP (units)", False),
    "Fewest workers (must meet demand)": ("Workers", False),
}


def bottleneck_index(line: Line) -> int:
    rates = start_rates(line)
    return min(range(len(rates)), key=lambda i: rates[i])


def best_allocation(line: Line, total_workers: int) -> Line:
    """Optimal spread of `total_workers` (max-min capacity), via greedy."""
    new = line.copy()
    for s in new.stations:
        s.workers = 1
    while sum(s.workers for s in new.stations) < total_workers:
        new.stations[bottleneck_index(new)].workers += 1
    return new


def _staffing_text(line: Line) -> str:
    return ", ".join(f"{s.name} {s.workers}" for s in line.stations)


def candidates(line: Line, max_workers: int, max_budget: float = 0.0) -> list:
    """Return [(name, what changes, kind, new_line)] without duplicates. Current line first."""
    n_now = sum(s.workers for s in line.stations)
    n_min = len(line.stations)
    out = [("Current line", "No change.", "Current", line.copy())]
    b = bottleneck_index(line)
    bname = line.stations[b].name

    # Quick single ideas
    l1 = line.copy()
    l1.stations[b].workers += 1
    out.append((f"Add 1 worker at {bname}", f"Hire one more worker for the bottleneck ({bname}).", "Single idea", l1))
    l2 = line.copy(buffer_size=line.buffer_size * 2)
    out.append((f"Double buffer space", f"Room between stations goes from {line.buffer_size} to "
                f"{line.buffer_size * 2} units.", "Single idea", l2))
    if line.stations[b].variation > 0:
        l3 = line.copy()
        l3.stations[b].variation = round(line.stations[b].variation / 2, 3)
        out.append((f"Standard work at {bname}", "Training, checklists or jigs make the bottleneck's time "
                    "more consistent (variation halved).", "Single idea", l3))

    # Best staffing for each total worker count
    best = {}
    for n in range(n_min, max(max_workers, n_min) + 1):
        ln = best_allocation(line, n)
        best[n] = ln
        out.append((f"Best staffing, {n} workers", f"Staffing: {_staffing_text(ln)}.", "Best staffing", ln))

    # Combinations of best staffing with the other levers
    for n in (n_now, n_now + 1):
        if n not in best:
            continue
        base = best[n]
        bb = bottleneck_index(base)
        bn = base.stations[bb].name
        buf = base.copy(buffer_size=line.buffer_size * 2)
        out.append((f"{n} workers + double buffer", f"Staffing: {_staffing_text(base)}; buffer "
                    f"{line.buffer_size * 2}.", "Combination", buf))
        if base.stations[bb].variation > 0:
            sw = base.copy()
            sw.stations[bb].variation = round(base.stations[bb].variation / 2, 3)
            out.append((f"{n} workers + standard work", f"Staffing: {_staffing_text(base)}; "
                        f"standard work at {bn}.", "Combination", sw))
            both = sw.copy(buffer_size=line.buffer_size * 2)
            out.append((f"{n} workers + standard work + double buffer", f"Staffing: {_staffing_text(base)}; "
                        f"standard work at {bn}; buffer {line.buffer_size * 2}.", "Combination", both))

    # Remove duplicates and anything over the limits (always keep the current line)
    seen, result = set(), []
    for name, why, kind, ln in out:
        sig = ln.signature()
        if sig in seen:
            continue
        workers = sum(s.workers for s in ln.stations)
        cost = analyze(ln)["labor_cost_per_hour"]
        if kind != "Current" and (workers > max_workers or (max_budget > 0 and cost > max_budget)):
            continue
        seen.add(sig)
        result.append((name, why, kind, ln))
    return result


def evaluate(line: Line, goal: str, max_workers: int = None, max_budget: float = 0.0,
             sim_hours=40.0, replications=5, seed=1, progress=None) -> list:
    """Simulate every candidate and return rows sorted best-first for the goal."""
    if max_workers is None:
        max_workers = sum(s.workers for s in line.stations) + 2
    col, higher_better = GOALS[goal]
    cands = candidates(line, max_workers, max_budget)
    rows, base_sim = [], None
    for k, (name, why, kind, ln) in enumerate(cands):
        r = simulate(ln, sim_hours=sim_hours, replications=replications, seed=seed)
        if base_sim is None:
            base_sim = r
        diff, half, sig = compare(base_sim, r)
        meets = (r["output_per_day"] >= line.demand_per_day) if line.demand_per_day > 0 else None
        rows.append({
            "Scenario": name,
            "Type": kind,
            "What changes": why,
            "Output/hour": r["output_per_hour"],
            "± (95%)": r["output_ci"],
            "Output/day": r["output_per_day"],
            "Meets demand": meets,
            "Avg WIP (units)": r["avg_wip"],
            "Avg flow time (min)": r["avg_flow_time"],
            "Workers": r["total_workers"],
            "Labor cost/hour": r["labor_cost_per_hour"],
            "Labor cost/unit": r["labor_cost_per_unit"],
            "Gain vs current (units/h)": diff,
            "Gain ±": half,
            "Clear difference?": "same" if kind == "Current" else ("yes" if sig else "no - could be luck"),
            "_line": ln,
            "_sim": r,
        })
        if progress:
            progress((k + 1) / len(cands), name)

    base = rows[0]
    for row in rows:
        row["Output change %"] = 100 * (row["Output/hour"] / base["Output/hour"] - 1)
        row["WIP change %"] = 100 * (row["Avg WIP (units)"] / base["Avg WIP (units)"] - 1)
        row["Cost/unit change %"] = (100 * (row["Labor cost/unit"] / base["Labor cost/unit"] - 1)
                                     if base["Labor cost/unit"] > 0 else 0.0)

    def sort_key(row):
        # With a demand target, scenarios that miss it go last
        penalty = 0 if row["Meets demand"] in (True, None) else 1
        v = row[col]
        tie = -row["Output/hour"]
        return (penalty, -v if higher_better else v, tie)

    return sorted(rows, key=sort_key)


def explain(best: dict, base: dict, demand: float) -> str:
    """Plain-English reason for the recommendation."""
    parts = [f"**{best['Scenario']}**: {best['What changes']}"]
    if best["Scenario"] == base["Scenario"]:
        return "The current line is already the best option for this goal within your limits."
    parts.append(f"Output goes from {base['Output/hour']:.1f} to {best['Output/hour']:.1f} good units/hour "
                 f"({best['Output change %']:+.0f}%).")
    if best["Clear difference?"] == "yes":
        parts.append(f"With 95% confidence the gain is {best['Gain vs current (units/h)']:.1f} "
                     f"± {best['Gain ±']:.1f} units/hour, so it is not just luck.")
    else:
        parts.append("The output difference is small enough that it could be random luck; "
                     "run more replications to be sure.")
    if base["Labor cost/unit"] > 0:
        parts.append(f"Labor cost per unit changes {best['Cost/unit change %']:+.0f}%, "
                     f"workers {base['Workers']} -> {best['Workers']}.")
    parts.append(f"Units in process (WIP) change {best['WIP change %']:+.0f}%.")
    if demand > 0:
        parts.append("It meets daily demand." if best["Meets demand"] else "It still does NOT meet daily demand.")
    return " ".join(parts)
