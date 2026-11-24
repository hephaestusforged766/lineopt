"""Instant (formula-based) analysis of a production line.

All times are in MINUTES per unit. A "station" is one step of the line.
Workers at the same station work in parallel on different units.
"""
from dataclasses import dataclass, field, replace


@dataclass
class Station:
    name: str
    task_time: float        # average minutes for ONE worker to finish ONE unit
    variation: float = 0.0  # coefficient of variation (0 = always same time, 0.3 = +-30% typical)
    workers: int = 1
    wage_per_hour: float = 0.0  # cost of one worker per hour

    @property
    def cycle_time(self) -> float:
        """Minutes between finished units at this station (more workers = faster)."""
        return self.task_time / self.workers

    @property
    def capacity_per_hour(self) -> float:
        return 60.0 / self.cycle_time


@dataclass
class Line:
    stations: list
    hours_per_day: float = 8.0
    demand_per_day: float = 0.0
    buffer_size: int = 5    # max units waiting between two stations

    def copy(self, **changes) -> "Line":
        new = replace(self, **changes)
        if "stations" not in changes:
            new.stations = [replace(s) for s in self.stations]
        return new


def validate(line: Line) -> list:
    """Return a list of plain-English problems (empty list = OK)."""
    problems = []
    if not line.stations:
        problems.append("Add at least one station.")
    for s in line.stations:
        if s.task_time <= 0:
            problems.append(f"'{s.name}': task time must be more than 0.")
        if s.workers < 1:
            problems.append(f"'{s.name}': needs at least 1 worker.")
        if s.variation < 0:
            problems.append(f"'{s.name}': variation cannot be negative.")
        if s.wage_per_hour < 0:
            problems.append(f"'{s.name}': wage cannot be negative.")
    if line.hours_per_day <= 0:
        problems.append("Hours per day must be more than 0.")
    if line.buffer_size < 1:
        problems.append("Buffer size must be at least 1.")
    return problems


def analyze(line: Line) -> dict:
    """Formula results, assuming no randomness (the 'best case')."""
    st = line.stations
    bottleneck = max(st, key=lambda s: s.cycle_time)
    line_ct = bottleneck.cycle_time
    output_per_hour = 60.0 / line_ct
    output_per_day = output_per_hour * line.hours_per_day
    takt = (line.hours_per_day * 60.0 / line.demand_per_day) if line.demand_per_day > 0 else None
    total_workers = sum(s.workers for s in st)
    labor_per_hour = sum(s.workers * s.wage_per_hour for s in st)
    work_content = sum(s.task_time for s in st)
    return {
        "bottleneck": bottleneck.name,
        "line_cycle_time": line_ct,
        "output_per_hour": output_per_hour,
        "output_per_day": output_per_day,
        "takt_time": takt,
        "meets_demand": (output_per_day >= line.demand_per_day) if line.demand_per_day > 0 else None,
        "total_workers": total_workers,
        "labor_cost_per_hour": labor_per_hour,
        "labor_cost_per_unit": labor_per_hour / output_per_hour,
        # Balance efficiency: share of paid worker-time that is real work
        "balance_efficiency": work_content / (total_workers * line_ct),
        "utilization": {s.name: s.cycle_time / line_ct for s in st},
    }
