"""Generate the SAMPLE stopwatch file data/sample_timestudy.csv (made-up, for demo only)."""
import csv
import random
from pathlib import Path

rng = random.Random(7)
# station: (mean seconds, sd seconds, observations)
plan = {"Mix dough": (240, 45, 20), "Shape": (360, 110, 20), "Bake": (300, 30, 15),
        "Pack": (180, 45, 20), "Label & box": (150, 30, 20)}
out = Path(__file__).resolve().parents[1] / "data" / "sample_timestudy.csv"
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["station", "time"])
    for st, (m, sd, n) in plan.items():
        for _ in range(n):
            w.writerow([st, max(20, round(rng.gauss(m, sd)))])
print("wrote", out)
