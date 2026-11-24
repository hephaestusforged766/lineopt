# LineOpt — Production Line Optimizer

A free Python app for small businesses and students. You enter the stations of a production line,
and LineOpt finds the **bottleneck**, **simulates** the line with realistic random variation, and
**ranks improvement scenarios** by the goal you choose (output, work-in-progress, cost, or workers).

Built with Python, [SimPy](https://simpy.readthedocs.io/) (discrete-event simulation), Streamlit, and Plotly.

## Run it

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

Command-line demo: `python run_sample.py` · Tests: `python -m pytest -q tests`

## What it does

| Tab | Output |
|---|---|
| Quick analysis | Bottleneck, max output, takt time, balance efficiency, labor cost per unit (formulas) |
| Simulation | Output with randomness, WIP, flow time, % working / blocked per station |
| Optimize | Tests and ranks: add a worker at the bottleneck, move a worker, double buffers, standard work (less variation), minimum staffing for demand |

## Example result (SAMPLE DATA — made up, not measured)

5-station bakery-style line, 8 h/day, demand 90 units/day, wage 70/hour (`data/sample_line.csv`).

| Scenario | Output/day | Change | Labor cost/unit | Workers | Meets demand |
|---|---|---|---|---|---|
| Current line | 80.3 | — | 41.83 | 6 | No |
| **Move 1 worker Pack → Shape** | **96.2** | **+20%** | **34.91 (−17%)** | 6 | **Yes** |
| Add a worker at Shape | 96.3 | +20% | 40.70 | 7 | Yes |
| Double buffer space | 80.2 | 0% | 41.87 | 6 | No |

Insight: hiring a 7th worker gives no more output than moving an existing one, because the
bottleneck shifts to *Bake*. More buffer space only raises WIP when the bottleneck is not starved.

## Method

- **Cycle time** = task time ÷ workers. **Bottleneck** = longest cycle time. **Takt time** = available time ÷ demand.
- Simulation: serial line, lognormal task times (mean and coefficient of variation from input),
  finite buffers with blocking, 2 h warm-up, 40 h measured, 5 replications averaged.
- Validation: with zero variation the simulation reproduces the formula output (test), and it satisfies
  Little's Law, WIP = throughput × flow time, within 5% (test).

## Limits

- Results above use sample data. No real business has been measured yet.
- Serial lines only (no rework, breakdowns, multiple products, or task-level rebalancing yet).
- Labor cost only; equipment, space, and training costs are not modeled.

## Credits

See [WORKLOG.md](WORKLOG.md) for what was done by me and what was AI-assisted.
