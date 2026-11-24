"""LineOpt - Streamlit app. Run with:  python -m streamlit run app.py"""
import hashlib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lineopt import balancing, timestudy
from lineopt.analysis import Line, Station, analyze, validate
from lineopt.optimizer import GOALS, evaluate, explain
from lineopt.simulation import simulate

st.set_page_config(page_title="LineOpt", layout="wide")
DATA = Path(__file__).parent / "data"
COLS = ["station", "task_time_min", "variation", "workers", "wage_per_hour",
        "defect_rate", "mtbf_min", "mttr_min"]
DEFAULTS = {"variation": 0.0, "workers": 1, "wage_per_hour": 0.0, "defect_rate": 0.0,
            "mtbf_min": 0.0, "mttr_min": 0.0}
COLUMN_CONFIG = {
    "station": st.column_config.TextColumn("Station", help="Name of the step. Must be unique.", required=True),
    "task_time_min": st.column_config.NumberColumn(
        "Task time (min)", min_value=0.01, format="%.2f",
        help="Average minutes for ONE worker to finish ONE unit. Use the Time study tab to measure it."),
    "variation": st.column_config.NumberColumn(
        "Variation", min_value=0.0, max_value=3.0, format="%.2f",
        help="How much the time changes from unit to unit (std dev / average). 0 = always the same; "
             "0.1 = very steady; 0.3 = normal manual work; 0.5+ = very uneven. The Time study tab computes it."),
    "workers": st.column_config.NumberColumn("Workers", min_value=1, step=1,
                                             help="People (or machines) doing this step side by side."),
    "wage_per_hour": st.column_config.NumberColumn("Wage ₱/hour", min_value=0.0, format="%.0f",
                                                   help="Cost of one worker per hour."),
    "defect_rate": st.column_config.NumberColumn(
        "Defect rate", min_value=0.0, max_value=0.99, format="%.3f",
        help="Share of units thrown away at this step. 0.02 = 2 out of 100."),
    "mtbf_min": st.column_config.NumberColumn(
        "Breaks every (min)", min_value=0.0, format="%.0f",
        help="Average working minutes between breakdowns (machine stops, missing tools). 0 = never."),
    "mttr_min": st.column_config.NumberColumn("Repair time (min)", min_value=0.0, format="%.0f",
                                              help="Average minutes to fix a breakdown. 0 = never breaks."),
}


def load_line_csv(src) -> pd.DataFrame:
    df = pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"station", "task_time_min"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(sorted(missing))}. "
                         "Download the template to see the expected format.")
    for c, v in DEFAULTS.items():
        if c not in df.columns:
            df[c] = v
    return df[COLS]


def set_stations(df: pd.DataFrame):
    st.session_state.stations_df = df.reset_index(drop=True)
    st.session_state.editor_ver = st.session_state.get("editor_ver", 0) + 1


def stations_from_df(df: pd.DataFrame) -> list:
    df = df.dropna(subset=["station", "task_time_min"]).copy()
    for c, v in DEFAULTS.items():
        df[c] = df[c].fillna(v)
    return [Station(str(r.station).strip(), float(r.task_time_min), float(r.variation), int(r.workers),
                    float(r.wage_per_hour), float(r.defect_rate), float(r.mtbf_min), float(r.mttr_min))
            for r in df.itertuples()]


def line_to_df(line: Line) -> pd.DataFrame:
    return pd.DataFrame([{"station": s.name, "task_time_min": s.task_time, "variation": s.variation,
                          "workers": s.workers, "wage_per_hour": s.wage_per_hour, "defect_rate": s.defect_rate,
                          "mtbf_min": s.mtbf, "mttr_min": s.mttr} for s in line.stations])


if "stations_df" not in st.session_state:
    set_stations(load_line_csv(DATA / "sample_line.csv"))
    st.session_state.is_sample = True

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Line settings")
    hours = st.number_input("Working hours per day", 0.5, 24.0, 8.0, 0.5)
    demand = st.number_input("Demand (good units per day, 0 = none)", 0.0, 100000.0, 90.0, 5.0)
    buffer_size = st.number_input("Buffer space between stations (units)", 1, 1000, 5,
                                  help="How many units can wait between two stations.")
    st.header("Simulation settings")
    sim_hours = st.slider("Hours to simulate per run", 8, 200, 40)
    reps = st.slider("Number of runs (replications)", 2, 20, 5,
                     help="More runs = narrower confidence intervals, but slower.")
    st.header("Data")
    up = st.file_uploader("Load stations from CSV", type="csv")
    if up is not None and st.session_state.get("last_upload") != up.file_id:
        try:
            set_stations(load_line_csv(up))
            st.session_state.is_sample = False
            st.session_state.last_upload = up.file_id
        except Exception as e:  # noqa: BLE001 - show any file problem to the user
            st.error(f"Could not read that file: {e}")
    if st.button("Reset to sample data"):
        set_stations(load_line_csv(DATA / "sample_line.csv"))
        st.session_state.is_sample = True
        st.rerun()
    st.download_button("Download CSV template", (DATA / "sample_line.csv").read_bytes(), "line_template.csv")

st.title("LineOpt — production line optimizer")
st.caption("Measure your process, balance it, find the bottleneck, and test improvements with simulation.")

tab_line, tab_sim, tab_opt, tab_ts, tab_bal, tab_guide = st.tabs(
    ["1 · Line & bottleneck", "2 · Simulate", "3 · Optimize", "Time study tool", "Line balancing tool", "Guide"])

# ---------------- Line ----------------
with tab_line:
    st.subheader("Your stations")
    if st.session_state.get("is_sample"):
        st.warning("SAMPLE DATA (made up for demonstration, not measured). Replace it with your own numbers, "
                   "or measure them in the **Time study tool** tab.")
    st.caption("Edit cells directly; add or delete rows at the bottom. Hover a column name for help.")
    edited = st.data_editor(st.session_state.stations_df, column_config=COLUMN_CONFIG, num_rows="dynamic",
                            width="stretch", key=f"editor_{st.session_state.editor_ver}", hide_index=True)

try:
    stations = stations_from_df(edited)
except (ValueError, TypeError) as e:
    st.error(f"Could not read the table: {e}")
    st.stop()

line = Line(stations, hours_per_day=hours, demand_per_day=demand, buffer_size=int(buffer_size))
problems = validate(line)
inputs_key = hashlib.md5(f"{edited.to_json()}|{hours}|{demand}|{buffer_size}|{sim_hours}|{reps}"
                         .encode()).hexdigest()

with tab_line:
    if problems:
        for p in problems:
            st.error(p)
    else:
        a = analyze(line)
        c = st.columns(5)
        c[0].metric("Bottleneck", a["bottleneck"], help="The station that limits the whole line.")
        c[1].metric("Max good output / hour", f"{a['output_per_hour']:.1f}")
        c[2].metric("Max good output / day", f"{a['output_per_day']:.0f}",
                    None if a["meets_demand"] is None else
                    ("meets demand" if a["meets_demand"] else f"{a['output_per_day'] - demand:.0f} vs demand"))
        c[3].metric("Balance efficiency", f"{a['balance_efficiency']:.0%}",
                    help="Share of paid worker time that is real work. 100% = perfectly balanced.")
        c[4].metric("Labor cost / good unit", f"₱{a['labor_cost_per_unit']:.2f}")
        names = [s.name for s in stations]
        eff_ct = [60 / s.capacity_per_hour for s in stations]
        fig = go.Figure(go.Bar(x=names, y=eff_ct, name="Effective cycle time",
                               marker_color=["#d9534f" if n == a["bottleneck"] else "#5b8def" for n in names]))
        if a["takt_time"]:
            fig.add_hline(y=a["takt_time"], line_dash="dash",
                          annotation_text=f"Takt time {a['takt_time']:.2f} min (pace needed for demand)")
        fig.update_layout(title="Minutes per unit at each station, incl. breakdown losses (red = bottleneck)",
                          yaxis_title="minutes / unit", height=380, margin=dict(t=50))
        st.plotly_chart(fig, width="stretch")
        if a["total_yield"] < 1:
            st.caption(f"Overall yield: {a['total_yield']:.1%} of started units become good units.")
        st.caption("Best case: these formulas ignore randomness and blocking. Tabs 2 and 3 show realistic results.")

if problems:
    with tab_sim:
        st.error("Fix the problems in tab 1 first.")
    with tab_opt:
        st.error("Fix the problems in tab 1 first.")
else:
    # ---------------- Simulate ----------------
    with tab_sim:
        st.write("Runs your line many times with random task times, breakdowns and defects.")
        if st.button("Run simulation", type="primary"):
            with st.spinner("Simulating..."):
                st.session_state.sim = (inputs_key, simulate(line, sim_hours=sim_hours, replications=reps))
        saved = st.session_state.get("sim")
        if saved and saved[0] != inputs_key:
            st.info("Your inputs changed since the last run. Click **Run simulation** to update.")
        elif saved:
            r = saved[1]
            c = st.columns(4)
            c[0].metric("Good output / hour", f"{r['output_per_hour']:.1f} ± {r['output_ci']:.1f}",
                        help="± = 95% confidence interval: the true average is very likely in this range.")
            c[1].metric("Good output / day", f"{r['output_per_day']:.0f}")
            c[2].metric("Avg WIP (units in process)", f"{r['avg_wip']:.1f}")
            c[3].metric("Avg flow time (min)", f"{r['avg_flow_time']:.1f}",
                        help="Minutes from starting a unit to finishing it.")
            if r["scrap_per_hour"] > 0:
                st.caption(f"Scrap: {r['scrap_per_hour']:.2f} units/hour thrown away.")
            names = list(r["utilization"])
            starved = [max(0.0, 1 - r["utilization"][n] - r["blocked_share"][n] - r["down_share"][n]) for n in names]
            fig = go.Figure([
                go.Bar(x=names, y=[r["utilization"][n] for n in names], name="Working", marker_color="#5b8def"),
                go.Bar(x=names, y=[r["down_share"][n] for n in names], name="Broken down", marker_color="#d9534f"),
                go.Bar(x=names, y=[r["blocked_share"][n] for n in names], name="Blocked (next buffer full)",
                       marker_color="#f0ad4e"),
                go.Bar(x=names, y=starved, name="Starved (waiting for work)", marker_color="#bbbbbb"),
            ])
            fig.update_layout(barmode="stack", title="How each station spends its time",
                              yaxis_tickformat=".0%", height=400, margin=dict(t=50))
            st.plotly_chart(fig, width="stretch")
            st.caption("Little's Law check: WIP ≈ output rate × flow time = "
                       f"{r['output_per_hour'] / 60 * r['avg_flow_time']:.1f} (simulated WIP {r['avg_wip']:.1f}).")
        else:
            st.info("Click **Run simulation**.")

    # ---------------- Optimize ----------------
    with tab_opt:
        n_now = sum(s.workers for s in stations)
        c = st.columns(3)
        goal = c[0].selectbox("Goal", list(GOALS))
        max_workers = c[1].number_input("Max workers allowed", len(stations), 200, n_now + 2)
        max_budget = c[2].number_input("Max labor budget ₱/hour (0 = no limit)", 0.0, 1e7, 0.0, 50.0)
        st.caption("The optimizer finds the best way to staff every station for each team size, combines it with "
                   "bigger buffers and standard work, simulates every option with the same random numbers, "
                   "and ranks them.")
        opt_key = f"{inputs_key}|{goal}|{max_workers}|{max_budget}"
        if st.button("Find improvements", type="primary"):
            bar = st.progress(0.0, "Starting...")
            rows = evaluate(line, goal, max_workers=int(max_workers), max_budget=max_budget,
                            sim_hours=sim_hours, replications=reps,
                            progress=lambda f, name: bar.progress(f, f"Simulated: {name}"))
            bar.empty()
            st.session_state.opt = (opt_key, rows)
        saved = st.session_state.get("opt")
        if saved and saved[0] != opt_key:
            st.info("Your inputs or goal changed. Click **Find improvements** to update.")
        elif saved:
            rows = saved[1]
            base = next(r for r in rows if r["Type"] == "Current")
            best = rows[0]
            st.success(explain(best, base, demand))
            if best is not base and st.button(f"Apply '{best['Scenario']}' to my line"):
                set_stations(line_to_df(best["_line"]))
                st.session_state.is_sample = False
                st.rerun()

            show = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
            cols = ["Scenario", "Type", "Output/hour", "± (95%)", "Output change %", "Clear difference?",
                    "Meets demand", "Workers", "Labor cost/unit", "Cost/unit change %", "Avg WIP (units)",
                    "Avg flow time (min)", "What changes"]
            st.dataframe(show[cols].style.format({
                "Output/hour": "{:.1f}", "± (95%)": "{:.1f}", "Avg WIP (units)": "{:.1f}",
                "Avg flow time (min)": "{:.1f}", "Labor cost/unit": "₱{:.2f}",
                "Output change %": "{:+.0f}%", "Cost/unit change %": "{:+.0f}%"}),
                width="stretch", hide_index=True)

            # Trade-off chart: output vs cost per unit
            color = {"Current": "#333333", "Single idea": "#f0ad4e", "Best staffing": "#5b8def",
                     "Combination": "#2ca02c"}
            fig = go.Figure()
            for kind, g in show.groupby("Type"):
                fig.add_trace(go.Scatter(
                    x=g["Labor cost/unit"], y=g["Output/hour"], mode="markers", name=kind,
                    marker=dict(size=12, color=color.get(kind)), text=g["Scenario"],
                    error_y=dict(type="data", array=g["± (95%)"], visible=True),
                    hovertemplate="%{text}<br>₱%{x:.2f}/unit<br>%{y:.1f} units/h<extra></extra>"))
            if demand > 0:
                fig.add_hline(y=demand / hours, line_dash="dash", annotation_text="Needed for demand")
            fig.update_layout(title="Trade-off: output vs labor cost per unit (up-left is better)",
                              xaxis_title="Labor cost per good unit (₱)", yaxis_title="Good units per hour",
                              height=440, margin=dict(t=50))
            st.plotly_chart(fig, width="stretch")
            st.download_button("Download results (CSV)", show.to_csv(index=False), "lineopt_results.csv")

# ---------------- Time study ----------------
with tab_ts:
    st.subheader("Time study: from stopwatch times to inputs")
    st.write("Upload a CSV with two columns, **station** and **time**: one row per unit you timed. "
             "The tool computes each station's average time and variation and tells you if you timed enough units.")
    c = st.columns(3)
    unit = c[0].radio("Times are in", ["seconds", "minutes"], horizontal=True)
    acc = c[1].select_slider("Wanted accuracy", options=[0.05, 0.10], value=0.05,
                             format_func=lambda x: f"±{x:.0%}")
    ts_file = c[2].file_uploader("Stopwatch CSV", type="csv", key="ts_upload")
    st.download_button("Download sample stopwatch file", (DATA / "sample_timestudy.csv").read_bytes(),
                       "sample_timestudy.csv")
    raw = None
    if ts_file is not None:
        raw = pd.read_csv(ts_file)
    elif st.checkbox("Use the SAMPLE stopwatch file (made up, for demo)"):
        raw = pd.read_csv(DATA / "sample_timestudy.csv")
        unit = "seconds"
    if raw is not None:
        try:
            summ = timestudy.summarize(raw, unit=unit, accuracy=acc)
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
            summ = None
        if summ is not None and len(summ):
            if summ.attrs.get("dropped_rows"):
                st.warning(f"Ignored {summ.attrs['dropped_rows']} rows with missing or non-positive times.")
            st.dataframe(summ.style.format({"avg_time_min": "{:.2f}", "std_dev_min": "{:.2f}",
                                            "variation": "{:.2f}", "ci95_min": "±{:.2f}", "min": "{:.2f}",
                                            "max": "{:.2f}"}), width="stretch", hide_index=True)
            short = summ[~summ["enough_data"]]
            if len(short):
                st.warning("Not enough observations for: " + ", ".join(
                    f"{r.station} (have {r.observations}, need {max(r.needed_observations, 10)})"
                    for r in short.itertuples()) + ". Results for these stations are less reliable.")
            if summ["outliers"].sum():
                st.info("Some times are outliers (unusually short or long). Check if they were mistakes "
                        "or real events, like a breakdown, before using the results.")
            fig = go.Figure([go.Box(y=raw[raw.iloc[:, 0] == s].iloc[:, 1] * (1 / 60 if unit == "seconds" else 1),
                                    name=s) for s in summ["station"]])
            fig.update_layout(title="Spread of observed times (minutes)", height=360, showlegend=False,
                              margin=dict(t=50))
            st.plotly_chart(fig, width="stretch")
            if st.button("Use these times in my line", type="primary"):
                cur = st.session_state.stations_df.set_index("station")
                new = []
                for r in summ.itertuples():
                    row = cur.loc[r.station].to_dict() if r.station in cur.index else dict(DEFAULTS)
                    row.update(station=r.station, task_time_min=round(r.avg_time_min, 3),
                               variation=round(r.variation, 3))
                    new.append(row)
                set_stations(pd.DataFrame(new)[COLS])
                st.session_state.is_sample = ts_file is None
                st.rerun()

# ---------------- Line balancing ----------------
with tab_bal:
    st.subheader("Line balancing: group tasks into stations")
    st.write("List every small task, its time, and which tasks must be done before it. The tool groups tasks "
             "into the fewest stations that keep up with demand (Ranked Positional Weight method).")
    if "tasks_df" not in st.session_state:
        st.session_state.tasks_df = pd.read_csv(DATA / "sample_tasks.csv")
    st.caption("SAMPLE tasks shown (made up). Predecessors: task IDs separated by ';'.")
    tasks_df = st.data_editor(st.session_state.tasks_df, num_rows="dynamic", width="stretch", hide_index=True,
                              key="tasks_editor", column_config={
                                  "task": st.column_config.TextColumn("Task ID", required=True),
                                  "description": st.column_config.TextColumn("Description"),
                                  "time_min": st.column_config.NumberColumn("Time (min)", min_value=0.01),
                                  "predecessors": st.column_config.TextColumn("Must come after")})
    default_takt = hours * 60 / demand if demand > 0 else 5.0
    takt = st.number_input("Takt time (min per unit)", 0.1, 1000.0, round(default_takt, 2),
                           help="From the sidebar: working minutes per day / demand. Change it to test other paces.")
    try:
        tasks = balancing.parse_tasks(tasks_df)
        tprobs = balancing.check_tasks(tasks)
    except Exception as e:  # noqa: BLE001
        tasks, tprobs = [], [str(e)]
    for p in tprobs:
        st.error(p)
    if tasks and not tprobs:
        res = balancing.balance(tasks, takt)
        c = st.columns(4)
        c[0].metric("Stations", len(res["stations"]))
        c[1].metric("Theoretical minimum", res["theoretical_min_stations"],
                    help="Total work ÷ takt time, rounded up. No solution can use fewer stations.")
        c[2].metric("Line efficiency", f"{res['efficiency']:.0%}")
        c[3].metric("Balance delay (idle share)", f"{res['balance_delay']:.0%}")
        bal = pd.DataFrame(res["stations"])
        st.dataframe(bal.style.format({"time_min": "{:.2f}", "idle_min": "{:.2f}"}), width="stretch",
                     hide_index=True)
        fig = go.Figure(go.Bar(x=bal["station"], y=bal["time_min"] / bal["workers"], text=bal["tasks"]))
        fig.add_hline(y=takt, line_dash="dash", annotation_text="Takt time")
        fig.update_layout(title="Work per worker at each station vs takt time", yaxis_title="minutes",
                          height=360, margin=dict(t=50))
        st.plotly_chart(fig, width="stretch")
        wage = float(st.session_state.stations_df["wage_per_hour"].fillna(0).median() or 0)
        if st.button("Use this balanced line as my stations", type="primary"):
            new = pd.DataFrame([{"station": f"{r['station']} ({r['tasks']})", "task_time_min": round(r["time_min"], 3),
                                 "variation": 0.2, "workers": r["workers"], "wage_per_hour": wage,
                                 "defect_rate": 0.0, "mtbf_min": 0.0, "mttr_min": 0.0} for r in res["stations"]])
            set_stations(new)
            st.session_state.is_sample = True
            st.rerun()
        st.caption("When applied, variation is set to 0.2 (typical manual work). Replace it with measured values.")

# ---------------- Guide ----------------
with tab_guide:
    st.markdown("""
### How to use LineOpt
1. **Measure** (optional): time 10–30 units per station with a stopwatch → *Time study tool* → *Use these times*.
2. **Design** (optional): list small tasks → *Line balancing tool* → *Use this balanced line*.
3. **Find the bottleneck**: tab 1.
4. **See reality**: tab 2 simulates randomness, breakdowns and defects.
5. **Improve**: tab 3 tests staffing, buffers and standard work, and recommends the best option for your goal.

### Key ideas
- **Cycle time** = minutes between finished units at a station = task time ÷ workers.
- **Availability** = time between breakdowns ÷ (time between breakdowns + repair time).
- **Bottleneck** = the station with the lowest capacity (after breakdowns and scrap). The line cannot go faster.
- **Takt time** = available minutes ÷ demand. Every station must work faster than this.
- **Yield** = share of started units that become good units.
- **WIP** = units started but not finished. **Flow time** = minutes from start to finish.
- **Little's Law**: WIP = output rate × flow time.
- **Blocked** = finished but the next buffer is full. **Starved** = nothing to work on.
- **95% confidence interval (±)**: the true long-run average is very likely inside this range.
- **Clear difference?**: compares each option with the current line using the same random numbers in
  every run (common random numbers); "yes" means the gain is bigger than random luck.
- **Optimal staffing**: adding each new worker to the most limiting station gives the best possible
  spread of workers for that team size.
- **Line balancing (RPW)**: tasks with the most work after them are placed first; each station is
  filled up to the takt time without breaking the task order.
""")
