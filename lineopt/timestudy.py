"""Time study: turn raw stopwatch times into average time and variation per station."""
import pandas as pd

from .stats import mean_ci, mean_sd, required_samples


def summarize(raw: pd.DataFrame, unit: str = "seconds", accuracy: float = 0.05) -> pd.DataFrame:
    """raw has columns 'station' and 'time' (one row per observed unit).

    Returns one row per station: n, mean (min), sd, variation (CV), 95% CI,
    outliers (outside 1.5 x IQR), and the observations needed for +-accuracy.
    """
    df = raw.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"station", "time"} <= set(df.columns):
        raise ValueError("The file needs two columns: 'station' and 'time'.")
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    bad = int(df["time"].isna().sum() + (df["time"] <= 0).sum())
    df = df[df["time"] > 0].dropna(subset=["station", "time"])
    factor = 1 / 60 if unit == "seconds" else 1.0
    rows = []
    for station, g in df.groupby("station", sort=False):
        t = (g["time"] * factor).tolist()
        m, sd = mean_sd(t)
        _, half = mean_ci(t)
        q1, q3 = pd.Series(t).quantile([0.25, 0.75])
        iqr = q3 - q1
        outliers = sum(1 for x in t if x < q1 - 1.5 * iqr or x > q3 + 1.5 * iqr)
        need = required_samples(m, sd, accuracy)
        rows.append({
            "station": str(station),
            "observations": len(t),
            "avg_time_min": m,
            "std_dev_min": sd,
            "variation": sd / m if m > 0 else 0.0,
            "ci95_min": half,
            "min": min(t),
            "max": max(t),
            "outliers": outliers,
            "needed_observations": need,
            "enough_data": len(t) >= max(need, 10),
        })
    out = pd.DataFrame(rows)
    out.attrs["dropped_rows"] = bad
    return out
