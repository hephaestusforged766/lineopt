"""Small statistics helpers (no SciPy needed)."""
import math

# Two-sided 95% Student-t critical values by degrees of freedom
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042,
        40: 2.021, 60: 2.000, 120: 1.980}


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    for k in sorted(_T95):
        if df <= k:
            return _T95[k]
    return 1.960


def mean_sd(xs):
    n = len(xs)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return m, sd


def mean_ci(xs):
    """Mean and half-width of the 95% confidence interval (nan if only 1 value)."""
    m, sd = mean_sd(xs)
    n = len(xs)
    return m, (t95(n - 1) * sd / math.sqrt(n)) if n > 1 else float("nan")


def paired_diff_ci(a, b):
    """Mean of (b - a), 95% half-width, and whether the difference is statistically clear."""
    d = [y - x for x, y in zip(a, b)]
    m, half = mean_ci(d)
    significant = (not math.isnan(half)) and abs(m) > half
    return m, half, significant


def required_samples(mean: float, sd: float, accuracy: float = 0.05) -> int:
    """Observations needed so the average is within +-accuracy (e.g. 5%) at 95% confidence."""
    if mean <= 0:
        return 0
    return math.ceil((1.96 * sd / (accuracy * mean)) ** 2)
