"""Run LineOpt on the SAMPLE line from the command line (no app needed)."""
import pandas as pd

from lineopt.analysis import Line, Station, analyze
from lineopt.optimizer import evaluate

df = pd.read_csv("data/sample_line.csv")
line = Line([Station(r.station, r.task_time_min, r.variation, r.workers, r.wage_per_hour)
             for r in df.itertuples()], hours_per_day=8, demand_per_day=90, buffer_size=5)
a = analyze(line)
print(f"SAMPLE DATA. Bottleneck: {a['bottleneck']}, max output/day: {a['output_per_day']:.0f}, demand: 90")
for goal in ["Most output per hour", "Lowest labor cost per unit"]:
    print(f"\nGoal: {goal}")
    for r in evaluate(line, goal):
        print(f"  {r['Scenario']:<36} out/day {r['Output/day']:6.1f} ({r['Output change %']:+4.0f}%)  "
              f"WIP {r['Avg WIP (units)']:5.1f}  cost/unit {r['Labor cost/unit']:6.2f}  "
              f"workers {r['Workers']}  meets demand: {r['Meets demand']}")
