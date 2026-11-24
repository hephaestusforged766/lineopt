"""Run LineOpt on the SAMPLE line from the command line (no app needed)."""
import sys

from lineopt.analysis import Line, Station, analyze
from lineopt.optimizer import evaluate, explain

import pandas as pd

df = pd.read_csv("data/sample_line.csv")
line = Line([Station(r.station, r.task_time_min, r.variation, r.workers, r.wage_per_hour,
                     r.defect_rate, r.mtbf_min, r.mttr_min) for r in df.itertuples()],
            hours_per_day=8, demand_per_day=90, buffer_size=5)
a = analyze(line)
print(f"SAMPLE DATA. Bottleneck: {a['bottleneck']}, max good output/day: {a['output_per_day']:.0f}, demand: 90")
goals = sys.argv[1:] or ["Most output per hour", "Lowest labor cost per unit", "Fewest workers (must meet demand)"]
for goal in goals:
    rows = evaluate(line, goal, sim_hours=40, replications=10)
    base = next(r for r in rows if r["Type"] == "Current")
    print(f"\nGoal: {goal}")
    print("  " + explain(rows[0], base, 90).replace("**", ""))
    for r in rows[:6] + [base]:
        print(f"  {r['Scenario']:<46} {r['Output/hour']:5.2f}±{r['± (95%)']:.2f}/h ({r['Output change %']:+4.0f}%) "
              f"cost/u {r['Labor cost/unit']:6.2f} ({r['Cost/unit change %']:+4.0f}%) WIP {r['Avg WIP (units)']:5.1f} "
              f"workers {r['Workers']} demand {r['Meets demand']} clear {r['Clear difference?']}")
