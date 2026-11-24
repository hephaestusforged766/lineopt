# LineOpt — Production Line Optimizer

**Live demo: https://lineopt.streamlit.app** (no install needed)

A free Python app for small businesses and IE students. Measure a process, balance it into stations,
find the **bottleneck**, **simulate** it with realistic randomness, breakdowns and defects, and let the
**optimizer** recommend the best staffing and improvements for your goal, with 95% confidence intervals.

Built with Python, [SimPy](https://simpy.readthedocs.io/) (discrete-event simulation), Streamlit, Plotly and pandas.

## Run it

```bash
git clone https://github.com/hephaestusforged766/lineopt.git
cd lineopt
pip install -r requirements.txt
python -m streamlit run app.py
```

Command-line demo: `python run_sample.py` · Tests: `python -m pytest -q tests`

## Features

| Tab | What it does | IE method |
|---|---|---|
| Time study tool | Upload stopwatch times → average time, variation, 95% CI, outliers, and how many more observations you need | Work measurement, sample-size formula n = (1.96·s / (e·x̄))² |
| Line balancing tool | Group small tasks (with "must come after" rules) into the fewest stations that meet takt time | Ranked Positional Weight (Helgeson–Birnie), efficiency, balance delay |
| 1 · Line & bottleneck | Bottleneck, max good output, takt time, balance efficiency, cost per unit | Capacity analysis incl. availability (MTBF/MTTR) and yield |
| 2 · Simulate | Output ± 95% CI, WIP, flow time, % working / broken / blocked / starved per station | Discrete-event simulation, replications, Little's Law check |
| 3 · Optimize | Ranks staffing for every team size, plus combinations with buffers and standard work, under worker and budget limits; plain-English recommendation; one-click apply | Simulation-optimization, common random numbers, paired confidence intervals |

## Example (SAMPLE DATA — made up, not measured)

5-station bakery-style line (`data/sample_line.csv`): 8 h/day, demand 90 good units/day, ₱70/hour wage,
2% defects at Shape, oven breaks about every 4 h of work (15 min repair). 10 replications × 40 h.

| Scenario | Good units/h (±95%) | Output | Labor cost/unit | Workers | WIP | Meets demand |
|---|---|---|---|---|---|---|
| Current line | 9.7 ± 0.1 | — | ₱43.38 | 6 | 9.5 | No |
| Best staffing, 5 workers | 9.7 ± 0.1 | +0% | ₱36.13 (−17%) | 5 | 9.5 | No |
| **Best staffing, 7 workers** | **14.6 ± 0.1** | **+51%** | **₱33.62 (−22%)** | 7 | **5.6 (−41%)** | **Yes** |
| Best staffing, 8 workers | 19.3 ± 0.1 | +99% | ₱29.06 (−33%) | 8 | 16.6 (+75%) | Yes |

Insights the tool surfaces:
- **Fewest workers that meet demand:** move one packer to Mix and add one at Shape/Bake (7 people). Output +51%,
  cost per unit −22%, and WIP drops 41%.
- One of the two packers is idle capacity: the same output is possible with 5 people (−17% cost per unit).
- Double buffers and standard work give **no clear gain** once staffing is right. The paired confidence
  interval shows the difference is within random luck.

## Method

- **Formulas:** cycle time = task time ÷ workers; availability A = MTBF ÷ (MTBF + MTTR); a station's
  capacity is adjusted for A and for scrap upstream; the bottleneck is the lowest capacity; takt = available time ÷ demand.
- **Simulation:** serial line, lognormal task times (mean + coefficient of variation), finite buffers with blocking,
  exponential breakdowns counted in working time, random scrap; 2 h warm-up; several replications.
- **Optimization:** for every team size N, workers are added one by one to the most limiting station.
  For this max-min problem this greedy rule is optimal (a test checks it against brute force).
  The best staffing levels are combined with bigger buffers and standard work, then every candidate is simulated.
- **Fair comparison:** each station has its own random-number stream, so every scenario sees the same
  "luck" (common random numbers). Gains are reported with a paired 95% confidence interval.
- **Validation (18 automated tests):** no-randomness simulation = formula output; Little's Law within 5%;
  simulated breakdown time ≈ 1 − A; simulated scrap ≈ defect rate; optimal staffing = brute force;
  line balancing respects takt time and task order.

## Limits

- All results above use sample data. No real business has been measured yet.
- Serial lines only: no parallel routes, multiple products, rework loops, or setup times.
- Labor cost only; equipment, space, and training costs are not modeled.
- Standard work is modeled as halving time variation. Its real effect must be measured.

## Credits

See [WORKLOG.md](WORKLOG.md) for what was done by me and what was AI-assisted.
