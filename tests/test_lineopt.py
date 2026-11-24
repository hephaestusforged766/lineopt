import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lineopt.analysis import Line, Station, analyze, validate
from lineopt.optimizer import evaluate, scenarios
from lineopt.simulation import simulate


def sample_line():
    return Line([Station("A", 4, 0, 1, 100), Station("B", 6, 0, 1, 100), Station("C", 3, 0, 1, 100)],
                hours_per_day=8, demand_per_day=90, buffer_size=5)


def test_bottleneck_and_output():
    a = analyze(sample_line())
    assert a["bottleneck"] == "B"
    assert math.isclose(a["output_per_hour"], 10.0)
    assert math.isclose(a["takt_time"], 480 / 90)
    assert a["meets_demand"] is False
    assert math.isclose(a["balance_efficiency"], 13 / 18)
    assert math.isclose(a["labor_cost_per_unit"], 30.0)


def test_more_workers_cut_cycle_time():
    s = Station("X", 6, 0, 2)
    assert s.cycle_time == 3


def test_validate_catches_bad_input():
    bad = Line([Station("X", 0, 0, 0)], buffer_size=0)
    assert len(validate(bad)) == 3


def test_simulation_matches_formula_without_randomness():
    # No variation -> simulated output should equal 60 / bottleneck cycle time
    r = simulate(sample_line(), sim_hours=40, replications=1)
    assert abs(r["output_per_hour"] - 10.0) < 0.2
    assert abs(r["utilization"]["B"] - 1.0) < 0.02


def test_variation_lowers_output():
    # Balanced line + tiny buffers: variation causes blocking/starving, so output < 60/5 = 12
    ln = Line([Station(n, 5, 0.5) for n in "ABCD"], buffer_size=1)
    r = simulate(ln, sim_hours=200, replications=3)
    assert r["output_per_hour"] < 11.0


def test_littles_law():
    ln = sample_line()
    for s in ln.stations:
        s.variation = 0.3
    r = simulate(ln, sim_hours=200, replications=2)
    lam = r["output_per_hour"] / 60  # per minute
    assert abs(r["avg_wip"] - lam * r["avg_flow_time"]) / r["avg_wip"] < 0.05


def test_scenarios_do_not_change_original():
    ln = sample_line()
    scenarios(ln)
    assert [s.workers for s in ln.stations] == [1, 1, 1]


def test_evaluate_ranks_by_output():
    rows = evaluate(sample_line(), "Most output per hour", sim_hours=20, replications=1)
    outs = [r["Output/hour"] for r in rows if r["Meets demand"]]
    assert outs == sorted(outs, reverse=True)
