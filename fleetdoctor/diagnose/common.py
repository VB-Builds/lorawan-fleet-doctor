from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from ..models import Uplink


@dataclass(frozen=True)
class Config:
    """Thresholds. They are defaults for a ~1 h uplink fleet, tune them per deployment."""

    min_uplinks: int = 20  # skip devices with less data than this
    loss_warn: float = 0.10  # fraction of expected uplinks missing
    loss_crit: float = 0.25
    reset_crit: int = 3
    margin_warn_db: float = 3.0  # link margin above demodulation floor
    margin_crit_db: float = 0.0
    drift_warn_db: float = 6.0  # RSSI drop, first vs last window
    drift_crit_db: float = 10.0
    sf_creep_warn: int = 2  # SF steps up
    sf_creep_crit: int = 3
    duty_limit: float = 0.01  # EU868 1 % sub-band duty cycle
    duty_warn_frac: float = 0.5  # warn at this fraction of the limit
    battery_empty_v: float = 2.5
    battery_warn_days: float = 60.0
    battery_crit_days: float = 14.0
    battery_min_days_data: float = 3.0
    battery_min_slope_v_day: float = 0.005  # ignore slower declines
    silent_k: float = 6.0  # silent after k expected intervals
    gateway_gap_min_s: float = 3600.0
    gateway_gap_crit_s: float = 3 * 3600.0


def by_device(uplinks: list[Uplink]) -> dict[str, list[Uplink]]:
    out: dict[str, list[Uplink]] = defaultdict(list)
    for u in uplinks:
        out[u.dev_eui].append(u)
    for series in out.values():
        series.sort(key=lambda u: u.time)
    return dict(out)


def edge_windows(series: list[Uplink]) -> tuple[list[Uplink], list[Uplink]]:
    """First and last window of a device series: min(24 h, a quarter of its span)."""
    span = series[-1].time - series[0].time
    width = min(timedelta(hours=24), span / 4)
    first = [u for u in series if u.time - series[0].time <= width]
    last = [u for u in series if series[-1].time - u.time <= width]
    return first, last


def med(values: list[float]) -> float:
    return float(median(values))


def theil_sen(xs: list[float], ys: list[float]) -> float:
    """Median of pairwise slopes: robust to outliers."""
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i])
              for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[j] != xs[i]]
    return med(slopes) if slopes else 0.0


def fmt_span(start: datetime, end: datetime) -> str:
    hours = (end - start).total_seconds() / 3600
    return f"{hours / 24:.0f} d" if hours >= 48 else f"{hours:.0f} h"
