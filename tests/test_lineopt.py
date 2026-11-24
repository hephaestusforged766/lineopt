import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lineopt import balancing, timestudy
from lineopt.analysis import Line, Station, analyze, validate
from lineopt.optimizer import best_allocation, candidates, evaluate
from lineopt.simulation import simulate
from lineopt.stats import paired_diff_ci, required_samples


def sample_line():
    return Line([Station("A", 4, 0, 1, 100), Station("B", 6, 0, 1, 100), Station("C", 3, 0, 1, 100)],
                hours_per_day=8, demand_per_day=90, buffer_size=5)


# ---------- formulas ----------
def test_bottleneck_and_output():
    a = analyze(sample_line())
    assert a["bottleneck"] == "B"
    assert math.isclose(a["output_per_hour"], 10.0)
    assert math.isclose(a["takt_time"], 480 / 90)
    assert a["meets_demand"] is False
    assert math.isclose(a["balance_efficiency"], 13 / 18)
    assert math.isclose(a["labor_cost_per_unit"], 30.0)


def test_availability_and_yield_in_formulas():
    s = Station("M", 5, mtbf=90, mttr=10)
    assert math.isclose(s.availability, 0.9)
    ln = Line([Station("A", 5, defect_rate=0.1), Station("B", 5.5)])
    # B sees only 90% of starts, so B allows 60/5.5/0.9 starts/h; A allows 12 -> A is bottleneck
    a = analyze(ln)
    assert a["bottleneck"] == "A"
    assert math.isclose(a["output_per_hour"], 12 * 0.9)


def test_validate_catches_bad_input():
    bad = Line([Station("X", 0, 0, 0), Station("X", 1, defect_rate=1.2, mtbf=10)], buffer_size=0)
    probs = validate(bad)
    assert any("different" in p for p in probs)
    assert any("defect" in p for p in probs)
    assert any("both" in p for p in probs)
    assert any("Buffer" in p for p in probs)


# ---------- simulation ----------
def test_simulation_matches_formula_without_randomness():
    r = simulate(sample_line(), sim_hours=40, replications=2)
    assert abs(r["output_per_hour"] - 10.0) < 0.2
    assert abs(r["utilization"]["B"] - 1.0) < 0.02


def test_variation_lowers_output():
    ln = Line([Station(n, 5, 0.5) for n in "ABCD"], buffer_size=1)
    r = simulate(ln, sim_hours=200, replications=3)
    assert r["output_per_hour"] < 11.0


def test_littles_law():
    ln = sample_line()
    for s in ln.stations:
        s.variation = 0.3
    r = simulate(ln, sim_hours=200, replications=2)
    lam = r["output_per_hour"] / 60
    assert abs(r["avg_wip"] - lam * r["avg_flow_time"]) / r["avg_wip"] < 0.05


def test_breakdowns_match_availability():
    # Single station, availability 0.8 -> about 12 * 0.8 = 9.6 units/h
    ln = Line([Station("M", 5, mtbf=40, mttr=10)])
    r = simulate(ln, sim_hours=400, replications=4)
    assert abs(r["output_per_hour"] - 9.6) < 0.4
    assert abs(r["down_share"]["M"] - 0.2) < 0.03


def test_defects_match_yield():
    ln = Line([Station("A", 5, defect_rate=0.2), Station("B", 1)])
    r = simulate(ln, sim_hours=400, replications=3)
    assert abs(r["output_per_hour"] - 12 * 0.8) < 0.3
    assert abs(r["scrap_per_hour"] - 12 * 0.2) < 0.3


def test_common_random_numbers_are_reproducible():
    ln = sample_line()
    ln.stations[1].variation = 0.4
    a = simulate(ln, sim_hours=20, replications=3, seed=5)
    b = simulate(ln, sim_hours=20, replications=3, seed=5)
    assert a["runs_output"] == b["runs_output"]


# ---------- statistics ----------
def test_paired_ci_detects_clear_gain():
    m, half, sig = paired_diff_ci([10, 11, 10.5, 10.2], [12, 13, 12.4, 12.1])
    assert sig and m > 1.5
    m, half, sig = paired_diff_ci([10, 11, 10.5, 10.2], [10.1, 10.8, 10.6, 10.2])
    assert not sig


def test_required_samples():
    assert required_samples(10, 2, 0.05) == math.ceil((1.96 * 2 / 0.5) ** 2)


# ---------- optimizer ----------
def test_best_allocation_is_optimal_by_brute_force():
    ln = Line([Station("A", 4), Station("B", 9), Station("C", 6), Station("D", 2)])
    for total in range(4, 10):
        greedy = analyze(best_allocation(ln, total))["output_per_hour"]
        best = 0
        import itertools
        for combo in itertools.product(range(1, total), repeat=4):
            if sum(combo) != total:
                continue
            t = ln.copy()
            for s, w in zip(t.stations, combo):
                s.workers = w
            best = max(best, analyze(t)["output_per_hour"])
        assert math.isclose(greedy, best)


def test_candidates_respect_limits_and_do_not_change_original():
    ln = sample_line()
    cands = candidates(ln, max_workers=4)
    assert all(sum(s.workers for s in c[3].stations) <= 4 for c in cands)
    assert [s.workers for s in ln.stations] == [1, 1, 1]
    sigs = [c[3].signature() for c in cands]
    assert len(sigs) == len(set(sigs))


def test_evaluate_ranks_by_output():
    rows = evaluate(sample_line(), "Most output per hour", sim_hours=20, replications=2)
    outs = [r["Output/hour"] for r in rows if r["Meets demand"]]
    assert outs == sorted(outs, reverse=True)


def test_fewest_workers_goal_meets_demand():
    rows = evaluate(sample_line(), "Fewest workers (must meet demand)", sim_hours=20, replications=2)
    assert rows[0]["Meets demand"]
    meeting = [r["Workers"] for r in rows if r["Meets demand"]]
    assert rows[0]["Workers"] == min(meeting)


# ---------- time study ----------
def test_timestudy_summary():
    raw = pd.DataFrame({"station": ["A"] * 4 + ["B"] * 3, "time": [60, 66, 54, 60, 120, 120, 120]})
    s = timestudy.summarize(raw, unit="seconds").set_index("station")
    assert math.isclose(s.loc["A", "avg_time_min"], 1.0)
    assert s.loc["B", "variation"] == 0
    assert not s.loc["A", "enough_data"]


# ---------- line balancing ----------
def test_balancing_respects_takt_and_order():
    tasks = balancing.parse_tasks(pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "sample_tasks.csv"))
    assert balancing.check_tasks(tasks) == []
    res = balancing.balance(tasks, takt=5.0)
    order = []
    for st in res["stations"]:
        assert st["time_min"] / st["workers"] <= 5.0 + 1e-9
        order += st["tasks"].split(" + ")
    pos = {t: i for i, t in enumerate(order)}
    for t in tasks:
        for p in t["preds"]:
            assert pos[p] < pos[t["task"]]
    assert len(res["stations"]) >= res["theoretical_min_stations"]


def test_balancing_detects_loop():
    tasks = [{"task": "A", "time": 1, "preds": ["B"]}, {"task": "B", "time": 1, "preds": ["A"]}]
    assert any("loop" in p for p in balancing.check_tasks(tasks))
