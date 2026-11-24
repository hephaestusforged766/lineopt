"""Instant (formula-based) analysis of a production line.

All times are in MINUTES. A "station" is one step of the line.
Workers at the same station work in parallel on different units.
"""
from dataclasses import dataclass, replace


@dataclass
class Station:
    name: str
    task_time: float          # average minutes for ONE worker to finish ONE unit
    variation: float = 0.0    # coefficient of variation (std dev / mean); 0 = always the same time
    workers: int = 1
    wage_per_hour: float = 0.0
    defect_rate: float = 0.0  # share of units scrapped at this station (0.02 = 2%)
    mtbf: float = 0.0         # mean minutes of WORK between breakdowns (0 = never breaks)
    mttr: float = 0.0         # mean minutes to repair a breakdown

    @property
    def availability(self) -> float:
        """Share of time the station can work (not broken). A = MTBF / (MTBF + MTTR)."""
        if self.mtbf <= 0 or self.mttr <= 0:
            return 1.0
        return self.mtbf / (self.mtbf + self.mttr)

    @property
    def yield_rate(self) -> float:
        return 1.0 - self.defect_rate

    @property
    def cycle_time(self) -> float:
        """Minutes between finished units at this station (more workers = faster)."""
        return self.task_time / self.workers

    @property
    def capacity_per_hour(self) -> float:
        """Units per hour this station can process, after breakdown losses."""
        return 60.0 / self.cycle_time * self.availability


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

    def signature(self) -> tuple:
        return (self.buffer_size, tuple((s.workers, s.variation) for s in self.stations))


def validate(line: Line) -> list:
    """Return a list of plain-English problems (empty list = OK)."""
    problems = []
    if not line.stations:
        problems.append("Add at least one station.")
    names = [s.name for s in line.stations]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        problems.append(f"Station names must be different: {', '.join(dupes)}.")
    for s in line.stations:
        if not s.task_time > 0:
            problems.append(f"'{s.name}': task time must be more than 0.")
        if s.workers < 1:
            problems.append(f"'{s.name}': needs at least 1 worker.")
        if not 0 <= s.variation <= 3:
            problems.append(f"'{s.name}': variation must be between 0 and 3.")
        if s.wage_per_hour < 0:
            problems.append(f"'{s.name}': wage cannot be negative.")
        if not 0 <= s.defect_rate < 1:
            problems.append(f"'{s.name}': defect rate must be from 0 to less than 1 (e.g. 0.02 = 2%).")
        if s.mtbf < 0 or s.mttr < 0:
            problems.append(f"'{s.name}': breakdown times cannot be negative.")
        if (s.mtbf > 0) != (s.mttr > 0):
            problems.append(f"'{s.name}': fill in both time-between-breakdowns and repair time, or neither.")
    if line.hours_per_day <= 0:
        problems.append("Hours per day must be more than 0.")
    if line.buffer_size < 1:
        problems.append("Buffer size must be at least 1.")
    return problems


def start_rates(line: Line) -> list:
    """Max START rate (units/hour entering station 1) that each station allows.

    Scrap upstream means a station sees fewer units than were started:
    station i receives start_rate * (yield of all stations before i).
    """
    rates, upstream_yield = [], 1.0
    for s in line.stations:
        rates.append(s.capacity_per_hour / upstream_yield)
        upstream_yield *= s.yield_rate
    return rates


def total_yield(line: Line) -> float:
    y = 1.0
    for s in line.stations:
        y *= s.yield_rate
    return y


def analyze(line: Line) -> dict:
    """Formula results, ignoring randomness and blocking (the 'best case')."""
    st = line.stations
    rates = start_rates(line)
    b = min(range(len(st)), key=lambda i: rates[i])
    start_rate = rates[b]
    output_per_hour = start_rate * total_yield(line)   # GOOD units per hour
    output_per_day = output_per_hour * line.hours_per_day
    takt = (line.hours_per_day * 60.0 / line.demand_per_day) if line.demand_per_day > 0 else None
    total_workers = sum(s.workers for s in st)
    labor_per_hour = sum(s.workers * s.wage_per_hour for s in st)
    work_content = sum(s.task_time for s in st)
    line_ct = 60.0 / start_rate
    return {
        "bottleneck": st[b].name,
        "line_cycle_time": line_ct,
        "output_per_hour": output_per_hour,
        "output_per_day": output_per_day,
        "takt_time": takt,
        "meets_demand": (output_per_day >= line.demand_per_day) if line.demand_per_day > 0 else None,
        "total_workers": total_workers,
        "labor_cost_per_hour": labor_per_hour,
        "labor_cost_per_unit": labor_per_hour / output_per_hour,
        "total_yield": total_yield(line),
        # Balance efficiency: share of paid worker-time that is real work (ignores scrap/breakdowns)
        "balance_efficiency": work_content / (total_workers * max(s.cycle_time for s in st)),
        # Utilization = how busy each station is when the line runs at the bottleneck's pace
        "utilization": {s.name: start_rate / r for s, r in zip(st, rates)},
    }
