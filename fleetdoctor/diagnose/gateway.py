"""Gateway outages: long silences on a gateway whose devices normally reach it."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ..models import Finding, Uplink
from .common import Config, by_device

NORMALLY_REACHES = 0.5  # a device "belongs" to gateways that hear >= half its uplinks
MIN_RX = 50


def gateway_times(uplinks: list[Uplink]) -> dict[str, list[datetime]]:
    out: dict[str, list[datetime]] = defaultdict(list)
    for u in uplinks:
        for r in u.rx:
            out[r.gateway_id].append(u.time)
    for times in out.values():
        times.sort()
    return dict(out)


def device_gateways(uplinks: list[Uplink]) -> dict[str, set[str]]:
    """Gateways that normally reach each device."""
    result: dict[str, set[str]] = {}
    for eui, series in by_device(uplinks).items():
        counts: dict[str, int] = defaultdict(int)
        for u in series:
            for r in u.rx:
                counts[r.gateway_id] += 1
        result[eui] = {g for g, c in counts.items() if c >= NORMALLY_REACHES * len(series)}
    return result


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    if not uplinks:
        return []
    end = max(u.time for u in uplinks)
    devices = by_device(uplinks)
    home = device_gateways(uplinks)
    findings: list[Finding] = []
    for gw, times in gateway_times(uplinks).items():
        if len(times) < MIN_RX:
            continue
        mean_gap = (times[-1] - times[0]).total_seconds() / (len(times) - 1)
        min_gap = max(cfg.gateway_gap_min_s, 15 * mean_gap)
        edges = list(zip(times, times[1:])) + [(times[-1], end)]
        for a, b in edges:
            gap = (b - a).total_seconds()
            if gap < min_gap:
                continue
            members = [e for e, g in home.items() if gw in g]
            rerouted = sum(1 for e in members if any(a < u.time < b for u in devices[e]))
            lost = len(members) - rerouted
            findings.append(Finding(
                gw, "gateway_outage", "critical" if gap >= cfg.gateway_gap_crit_s else "warning",
                f"Gateway heard nothing for {gap / 3600:.1f} h ({a:%Y-%m-%d %H:%M} -> "
                f"{b:%Y-%m-%d %H:%M} UTC) while its usual rate is one uplink per "
                f"{mean_gap:.0f} s; {len(members)} devices normally reach it: {rerouted} "
                f"rerouted via another gateway, {lost} not heard by any gateway during the outage",
                "Check gateway power, backhaul and its packet-forwarder/Basics Station "
                "connection; devices with a single gateway in range had no coverage.",
                kind="gateway"))
    return findings
