"""Spreading-factor creep: ADR pushing a device to slower, longer-airtime data rates."""
from __future__ import annotations

from ..models import Finding, Uplink
from .airtime import time_on_air
from .common import Config, by_device, edge_windows, med
from .link import MIN_WINDOW


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    for eui, series in by_device(uplinks).items():
        if len(series) < cfg.min_uplinks:
            continue
        first, last = edge_windows(series)
        if len(first) < MIN_WINDOW or len(last) < MIN_WINDOW:
            continue
        sf_then, sf_now = round(med([u.sf for u in first])), round(med([u.sf for u in last]))
        steps = sf_now - sf_then
        if steps < cfg.sf_creep_warn:
            continue
        phy = round(med([u.phy_len for u in last]))
        t_then, t_now = time_on_air(phy, sf_then), time_on_air(phy, sf_now)
        findings.append(Finding(
            eui, "sf_creep", "critical" if steps >= cfg.sf_creep_crit else "warning",
            f"Spreading factor crept SF{sf_then} -> SF{sf_now}: time on air per uplink "
            f"{t_then * 1000:.0f} ms -> {t_now * 1000:.0f} ms (x{t_now / t_then:.1f}), "
            f"battery and duty-cycle cost rises accordingly",
            "Find out why the link got worse (see link_drift); fix the path rather than "
            "letting ADR pay for it in airtime."))
    return findings
