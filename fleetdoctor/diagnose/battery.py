"""Battery decline forecast: robust (Theil-Sen) fit on daily medians -> days to empty."""
from __future__ import annotations

from collections import defaultdict

from ..models import Finding, Uplink
from .common import Config, by_device, med, theil_sen


def forecast(series: list[Uplink], cfg: Config) -> tuple[float, float, float] | None:
    """(slope V/day, current V, days to empty) or None if there is not enough data."""
    pts = [(u.time, u.battery_v) for u in series if u.battery_v is not None]
    if len(pts) < cfg.min_uplinks:
        return None
    t0 = pts[0][0]
    days: dict[int, list[float]] = defaultdict(list)
    for t, v in pts:
        days[int((t - t0).total_seconds() // 86400)].append(v)  # type: ignore[arg-type]
    daily = [(d + 0.5, med(vs)) for d, vs in sorted(days.items()) if len(vs) >= 3]
    if len(daily) < 3 or daily[-1][0] - daily[0][0] < cfg.battery_min_days_data - 1:
        return None
    slope = theil_sen([d for d, _ in daily], [v for _, v in daily])
    current = med([v for _, v in daily[-2:]])
    if slope >= 0:
        return slope, current, float("inf")
    return slope, current, max(current - cfg.battery_empty_v, 0.0) / -slope


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    for eui, series in by_device(uplinks).items():
        result = forecast(series, cfg)
        if result is None:
            continue
        slope, current, left = result
        if -slope < cfg.battery_min_slope_v_day or left > cfg.battery_warn_days:
            continue
        findings.append(Finding(
            eui, "battery", "critical" if left <= cfg.battery_crit_days else "warning",
            f"Battery at {current:.2f} V falling {-slope * 1000:.0f} mV/day: about {left:.0f} days "
            f"until {cfg.battery_empty_v:.1f} V",
            "Schedule a battery swap before the forecast date; check for a stuck-on "
            "peripheral or a reboot loop if the decline is steeper than the fleet."))
    return findings
