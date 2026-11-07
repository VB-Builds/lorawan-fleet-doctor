"""Per-device airtime against the sub-band duty cycle (EU868: 1 %)."""
from __future__ import annotations

from ..models import Finding, Uplink
from .airtime import uplink_airtime
from .common import Config, by_device, fmt_span

WINDOW_S = 3600.0


def peak_duty(series: list[Uplink]) -> tuple[float, float]:
    """(average duty over the whole series, peak duty over any sliding hour)."""
    toa = [uplink_airtime(u) for u in series]
    ts = [u.time.timestamp() for u in series]
    total_span = max(ts[-1] - ts[0], WINDOW_S)
    peak = acc = 0.0
    lo = 0
    for hi, t in enumerate(ts):
        acc += toa[hi]
        while t - ts[lo] > WINDOW_S:
            acc -= toa[lo]
            lo += 1
        peak = max(peak, acc / WINDOW_S)
    return sum(toa) / total_span, peak


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    for eui, series in by_device(uplinks).items():
        if len(series) < cfg.min_uplinks:
            continue
        avg, peak = peak_duty(series)
        if peak < cfg.duty_limit * cfg.duty_warn_frac:
            continue
        per_uplink = uplink_airtime(series[-1])
        interval_min = (series[-1].time - series[0].time).total_seconds() / 60 / (len(series) - 1)
        findings.append(Finding(
            eui, "duty_cycle", "critical" if peak >= cfg.duty_limit else "warning",
            f"Airtime peaks at {peak:.2%} of an hour (limit {cfg.duty_limit:.0%}), average "
            f"{avg:.2%} over {fmt_span(series[0].time, series[-1].time)}: "
            f"{per_uplink:.2f} s per uplink (SF{series[-1].sf}, {series[-1].phy_len} B) "
            f"every {interval_min:.1f} min",
            "Lengthen the reporting interval, shrink the payload or move to a lower SF; "
            "sending above the duty cycle is a regulatory problem, not only a battery one."))
    return findings
