"""Silent devices: no uplink for more than k x the device's own reporting interval."""
from __future__ import annotations

from ..models import Finding, Uplink
from .common import Config, by_device, med


def expected_interval_s(series: list[Uplink]) -> float:
    """Median spacing of consecutive frames (FCnt step of 1); falls back to all spacings."""
    steps = [(b.time - a.time).total_seconds() for a, b in zip(series, series[1:])
             if b.f_cnt - a.f_cnt == 1]
    if len(steps) < 5:
        steps = [(b.time - a.time).total_seconds() for a, b in zip(series, series[1:])]
    return med(steps)


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    if not uplinks:
        return []
    now = max(u.time for u in uplinks)
    findings: list[Finding] = []
    for eui, series in by_device(uplinks).items():
        if len(series) < cfg.min_uplinks:
            continue
        interval = expected_interval_s(series)
        quiet = (now - series[-1].time).total_seconds()
        if interval <= 0 or quiet <= cfg.silent_k * interval:
            continue
        findings.append(Finding(
            eui, "silent", "critical" if quiet > 4 * cfg.silent_k * interval else "warning",
            f"No uplink for {quiet / 3600:.1f} h = {quiet / interval:.0f}x its usual interval of "
            f"{interval / 60:.0f} min (last seen {series[-1].time:%Y-%m-%d %H:%M} UTC, "
            f"last FCnt {series[-1].f_cnt}, battery "
            f"{'%.2f V' % series[-1].battery_v if series[-1].battery_v else 'unknown'})",
            "Check power and the last known battery level first, then the gateways it "
            "normally reaches (see gateway_outage), then the site."))
    return findings
