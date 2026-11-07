"""Markdown + JSON fleet report: worst problems first, per-gateway table."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from statistics import median

from .diagnose.gateway import device_gateways
from .models import Finding, Uplink

SEVERITY_ORDER = {"critical": 0, "warning": 1}
CHECK_ORDER = ["gateway_outage", "silent", "battery", "duty_cycle", "fcnt_gaps", "fcnt_reset",
               "link_margin", "link_drift", "sf_creep"]


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity],
                                           CHECK_ORDER.index(f.check) if f.check in CHECK_ORDER else 99,
                                           f.subject))


def gateway_table(uplinks: list[Uplink], findings: list[Finding]) -> list[dict[str, object]]:
    heard: dict[str, list[Uplink]] = defaultdict(list)
    for u in uplinks:
        for r in u.rx:
            heard[r.gateway_id].append(u)
    homes = device_gateways(uplinks)
    outages = Counter(f.subject for f in findings if f.check == "gateway_outage")
    rows = []
    for gw, ups in sorted(heard.items()):
        rx = [r for u in ups for r in u.rx if r.gateway_id == gw]
        rows.append({
            "gateway": gw,
            "uplinks": len(ups),
            "devices": len({u.dev_eui for u in ups}),
            "home_devices": sum(1 for g in homes.values() if gw in g),
            "median_rssi": round(median(r.rssi for r in rx), 1),
            "median_snr": round(median(r.snr for r in rx), 1),
            "outages": outages.get(gw, 0),
        })
    return rows


def build(uplinks: list[Uplink], findings: list[Finding]) -> dict[str, object]:
    ranked = rank(findings)
    return {
        "window": {"start": min(u.time for u in uplinks).isoformat() if uplinks else None,
                   "end": max(u.time for u in uplinks).isoformat() if uplinks else None},
        "uplinks": len(uplinks),
        "devices": len({u.dev_eui for u in uplinks}),
        "gateways": gateway_table(uplinks, findings),
        "summary": dict(Counter(f.severity for f in findings)),
        "by_check": dict(Counter(f.check for f in findings)),
        "findings": [f.to_dict() for f in ranked],
    }


def to_json(uplinks: list[Uplink], findings: list[Finding]) -> str:
    return json.dumps(build(uplinks, findings), indent=2)


def to_markdown(uplinks: list[Uplink], findings: list[Finding], top: int = 30) -> str:
    rep = build(uplinks, findings)
    win = rep["window"]
    lines = [
        "# LoRaWAN fleet report", "",
        f"{rep['uplinks']} uplinks from {rep['devices']} devices via {len(rep['gateways'])} "
        f"gateways, {str(win['start'])[:16]} to {str(win['end'])[:16]} UTC.", "",
        f"**{rep['summary'].get('critical', 0)} critical, {rep['summary'].get('warning', 0)} "
        f"warnings.** " + ", ".join(f"{c} {n}" for c, n in sorted(rep["by_check"].items())), "",
        "## Top problems", "",
    ]
    ranked = rank(findings)
    for f in ranked[:top]:
        lines += [f"- **[{f.severity.upper()}] {f.check}** `{f.subject}` - {f.evidence}",
                  f"  - Suggestion: {f.suggestion}"]
    if len(ranked) > top:
        lines.append(f"- ... {len(ranked) - top} more in the JSON report")
    if not ranked:
        lines.append("- Nothing above the configured thresholds.")
    lines += ["", "## Gateways", "",
              "| Gateway | Uplinks heard | Devices heard | Regular devices | Median RSSI | Median SNR | Outages |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for g in rep["gateways"]:
        lines.append(f"| `{g['gateway']}` | {g['uplinks']} | {g['devices']} | {g['home_devices']} "
                     f"| {g['median_rssi']} | {g['median_snr']} | {g['outages']} |")
    return "\n".join(lines) + "\n"
