"""LineOpt - Streamlit app. Run with:  python -m streamlit run app.py"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lineopt.analysis import Line, Station, analyze, validate
from lineopt.optimizer import GOALS, evaluate
from lineopt.simulation import simulate

st.set_page_config(page_title="LineOpt", layout="wide")
st.title("LineOpt - production line optimizer")
st.caption("Enter your stations, find the bottleneck, and test improvements with simulation.")

SAMPLE = Path(__file__).parent / "data" / "sample_line.csv"
COLS = ["station", "task_time_min", "variation", "workers", "wage_per_hour"]

# ---------- Inputs ----------
with st.sidebar:
    st.header("1. Line settings")
    hours = st.number_input("Working hours per day", 0.5, 24.0, 8.0, 0.5)
    demand = st.number_input("Demand (units per day, 0 = none)", 0.0, 100000.0, 90.0, 5.0)
    buffer_size = st.number_input("Buffer space between stations (units)", 1, 1000, 5)
    st.header("2. Simulation settings")
    sim_hours = st.slider("Hours to simulate per run", 8, 200, 40)
    reps = st.slider("Number of runs (replications)", 1, 20, 5)
    goal = st.selectbox("Optimization goal", list(GOALS))
    uploaded = st.file_uploader("Load stations from CSV", type="csv")
    st.download_button("Download CSV template", SAMPLE.read_bytes(), "line_template.csv")

st.subheader("Stations (edit the table)")
st.write("**task_time_min** = minutes for one worker to finish one unit. "
         "**variation** = how much the time changes (0 = always the same, 0.3 = about +-30%).")
if uploaded is not None:
    df0 = pd.read_csv(uploaded)
    st.info("Using your uploaded file.")
else:
    df0 = pd.read_csv(SAMPLE)
    st.warning("SAMPLE DATA (made up for demonstration, not measured). Replace with your own.")
df = st.data_editor(df0[COLS], num_rows="dynamic", width="stretch", key="stations")

try:
    df = df.dropna(subset=["station", "task_time_min"])
    stations = [Station(str(r.station), float(r.task_time_min), float(r.variation or 0),
                        int(r.workers or 1), float(r.wage_per_hour or 0)) for r in df.itertuples()]
except (ValueError, TypeError) as e:
    st.error(f"Could not read the table: {e}")
    st.stop()

line = Line(stations, hours_per_day=hours, demand_per_day=demand, buffer_size=int(buffer_size))
problems = validate(line)
if problems:
    for p in problems:
        st.error(p)
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["Quick analysis", "Simulation", "Optimize", "How it works"])

# ---------- Quick analysis ----------
with tab1:
    a = analyze(line)
    c = st.columns(5)
    c[0].metric("Bottleneck", a["bottleneck"])
    c[1].metric("Max output / hour", f"{a['output_per_hour']:.1f}")
    c[2].metric("Max output / day", f"{a['output_per_day']:.0f}",
                None if a["meets_demand"] is None else
                ("meets demand" if a["meets_demand"] else f"{a['output_per_day'] - demand:.0f} vs demand"))
    c[3].metric("Balance efficiency", f"{a['balance_efficiency']:.0%}")
    c[4].metric("Labor cost / unit", f"{a['labor_cost_per_unit']:.2f}")

    names = [s.name for s in stations]
    fig = go.Figure(go.Bar(x=names, y=[s.cycle_time for s in stations], name="Cycle time",
                           marker_color=["#d9534f" if n == a["bottleneck"] else "#5b8def" for n in names]))
    if a["takt_time"]:
        fig.add_hline(y=a["takt_time"], line_dash="dash",
                      annotation_text=f"Takt time {a['takt_time']:.2f} min (needed pace)")
    fig.update_layout(title="Minutes per unit at each station (red = bottleneck)",
                      yaxis_title="minutes / unit", height=380)
    st.plotly_chart(fig, width="stretch")
    st.caption("Best case: these formulas ignore randomness. The Simulation tab shows realistic results.")

# ---------- Simulation ----------
with tab2:
    if st.button("Run simulation", type="primary"):
        with st.spinner("Simulating..."):
            st.session_state["sim"] = simulate(line, sim_hours=sim_hours, replications=reps)
    r = st.session_state.get("sim")
    if r:
        c = st.columns(4)
        c[0].metric("Output / hour", f"{r['output_per_hour']:.1f}", f"+-{r['output_per_hour_sd']:.1f} (run-to-run)",
                    delta_color="off")
        c[1].metric("Output / day", f"{r['output_per_day']:.0f}")
        c[2].metric("Avg WIP (units in process)", f"{r['avg_wip']:.1f}")
        c[3].metric("Avg flow time (min)", f"{r['avg_flow_time']:.1f}")
        names = list(r["utilization"])
        fig = go.Figure([
            go.Bar(x=names, y=[r["utilization"][n] for n in names], name="Working"),
            go.Bar(x=names, y=[r["blocked_share"][n] for n in names], name="Blocked (next buffer full)"),
        ])
        fig.update_layout(barmode="stack", title="How each station spends its time",
                          yaxis_tickformat=".0%", height=380)
        st.plotly_chart(fig, width="stretch")
        st.caption("The rest of the time (not shown) is starved: waiting for a unit to arrive.")
    else:
        st.info("Click **Run simulation**.")

# ---------- Optimize ----------
with tab3:
    st.write(f"Goal: **{goal}**. The app tests each change with the simulation and ranks them.")
    if st.button("Find improvements", type="primary"):
        with st.spinner("Testing scenarios..."):
            st.session_state["opt"] = evaluate(line, goal, sim_hours=sim_hours, replications=reps)
            st.session_state["opt_goal"] = goal
    rows = st.session_state.get("opt")
    if rows:
        best = rows[0]
        st.success(f"Best for '{st.session_state['opt_goal']}': **{best['Scenario']}** - "
                   f"output {best['Output change %']:+.0f}%, WIP {best['WIP change %']:+.0f}%, "
                   f"cost/unit {best['Cost/unit change %']:+.0f}%, workers {best['Workers']}.")
        show = pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")} for row in rows])
        st.dataframe(show.style.format({
            "Output/hour": "{:.1f}", "Output/day": "{:.0f}", "Avg WIP (units)": "{:.1f}",
            "Avg flow time (min)": "{:.1f}", "Labor cost/unit": "{:.2f}",
            "Output change %": "{:+.0f}%", "WIP change %": "{:+.0f}%", "Cost/unit change %": "{:+.0f}%"}),
            width="stretch", hide_index=True)
        fig = go.Figure(go.Bar(x=show["Scenario"], y=show["Output/day"]))
        if demand > 0:
            fig.add_hline(y=demand, line_dash="dash", annotation_text="Demand")
        fig.update_layout(title="Output per day by scenario", height=380)
        st.plotly_chart(fig, width="stretch")
        st.download_button("Download results (CSV)", show.to_csv(index=False), "lineopt_results.csv")

# ---------- Explanation ----------
with tab4:
    st.markdown("""
- **Cycle time** = minutes between finished units at a station = task time / workers.
- **Bottleneck** = the station with the longest cycle time. The whole line cannot go faster.
- **Takt time** = available minutes / demand. Every station must be faster than this to meet demand.
- **Balance efficiency** = total work minutes / (workers x bottleneck cycle time). 100% = no idle time.
- **WIP (work-in-progress)** = units started but not finished.
- **Flow time** = minutes from start to finish for one unit. Little's Law: WIP = output rate x flow time.
- **Simulation**: random task times (lognormal), limited buffers, workers get *blocked* when the next buffer is full
  and *starved* when nothing arrives. Several runs are averaged.
""")
