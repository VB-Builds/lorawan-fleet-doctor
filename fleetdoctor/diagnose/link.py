"""Link margin vs the SF demodulation floor, and RSSI/SNR drift."""
from __future__ import annotations

from ..models import Finding, Uplink
from .airtime import snr_margin
from .common import Config, by_device, edge_windows, med

MIN_WINDOW = 6


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    for eui, series in by_device(uplinks).items():
        if len(series) < cfg.min_uplinks:
            continue
        first, last = edge_windows(series)
        if len(first) < MIN_WINDOW or len(last) < MIN_WINDOW:
            continue
        margin = med([snr_margin(u.best.snr, u.sf) for u in last])
        sf_now = int(med([u.sf for u in last]))
        if margin < cfg.margin_warn_db:
            findings.append(Finding(
                eui, "link_margin", "critical" if margin < cfg.margin_crit_db else "warning",
                f"Link margin {margin:+.1f} dB above the SF{sf_now} demodulation floor "
                f"(median SNR {med([u.best.snr for u in last]):.1f} dB, last window); "
                f"ADR normally keeps ~10 dB",
                "Move the device/antenna or add a gateway; this device cannot go to a higher SF "
                "if it is already at SF12." if sf_now == 12 else
                "Check antenna and placement; a higher SF buys margin at the cost of airtime."))
        rssi_drop = med([u.best.rssi for u in first]) - med([u.best.rssi for u in last])
        snr_drop = med([u.best.snr for u in first]) - med([u.best.snr for u in last])
        if rssi_drop >= cfg.drift_warn_db:
            findings.append(Finding(
                eui, "link_drift", "critical" if rssi_drop >= cfg.drift_crit_db else "warning",
                f"RSSI drifted down {rssi_drop:.1f} dB (SNR {snr_drop:.1f} dB lower) between "
                f"the first and last window of the data",
                "Something changed on the path: new obstruction, water ingress, antenna "
                "damage or a moved gateway. Inspect the site."))
    return findings
