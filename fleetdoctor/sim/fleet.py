"""Deterministic fleet simulator with injected, labelled faults.

Model: every device has a home gateway (always hears it) and 0-2 secondary gateways (hear it
75 % of the time, 3-10 dB weaker). ADR keeps ~10 dB margin on the nominal SNR and only ever
steps the spreading factor up. Payloads are Cayenne LPP (battery on channel 1).
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..diagnose.airtime import DEMOD_FLOOR_DB
from ..models import Rx, Uplink

START = datetime(2026, 3, 2, tzinfo=timezone.utc)
ADR_MARGIN_DB = 10.0
HOURS = timedelta(hours=1)


@dataclass
class Truth:
    """What was injected: list of {subject, check, note}."""

    faults: list[dict[str, str]] = field(default_factory=list)

    def add(self, subject: str, check: str, note: str) -> None:
        self.faults.append({"subject": subject, "check": check, "note": note})

    def pairs(self) -> set[tuple[str, str]]:
        return {(f["subject"], f["check"]) for f in self.faults}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.faults, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Truth":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Dev:
    eui: str
    interval_s: float
    home: int
    secondary: list[tuple[int, float]]
    snr0: float
    fcnt0: int = 0
    wrap16: bool = False
    batt0: float = 3.6
    batt_slope: float = -0.0004  # V/day
    loss_final: float = 0.0  # extra loss probability reached at the end
    drop_at: float | None = None  # fraction of span: instant SNR drop (obstruction)
    drop_db: float = 0.0
    ramp: tuple[float, float] | None = None  # fraction span over which drop_db ramps in
    stop_at: float | None = None  # silent after this fraction
    resets_at: tuple[float, ...] = ()
    app_len: int = 8


def _adr_sf(snr: float) -> int:
    return next((sf for sf in range(7, 13) if snr - DEMOD_FLOOR_DB[sf] >= ADR_MARGIN_DB), 12)


def _payload(volts: float, temp_c: float, size: int) -> bytes:
    data = bytes([1, 0x02]) + round(volts * 100).to_bytes(2, "big", signed=True)
    data += bytes([2, 0x67]) + round(temp_c * 10).to_bytes(2, "big", signed=True)
    ch = 3
    while len(data) < size:  # padding channels (extra temperature readings)
        data += bytes([ch, 0x67, 0, 200])
        ch += 1
    return data


def _build_devices(n: int, n_gw: int, rng: random.Random) -> list[Dev]:
    devs = []
    for i in range(n):
        home = rng.randrange(n_gw)
        others = [g for g in range(n_gw) if g != home]
        sec = [(g, rng.uniform(3, 10)) for g in rng.sample(others, rng.choice([0, 1, 1, 2]))]
        wrap = i % 67 == 5
        devs.append(Dev(
            eui=f"d3b0{i + 1:012x}", interval_s=rng.choice([1800, 3600, 3600]), home=home,
            secondary=sec, snr0=rng.uniform(-12, 14),
            fcnt0=65536 - rng.randint(15, 60) if wrap else rng.randint(0, 5000), wrap16=wrap,
            batt0=rng.uniform(3.55, 3.65)))
    return devs


def _inject_faults(devs: list[Dev], rng: random.Random, truth: Truth) -> None:
    pool = rng.sample(devs, 14)
    it = iter(pool)
    for (b0, slope) in [(3.25, -0.06), (3.40, -0.03), (3.50, -0.02)]:
        d = next(it)
        d.batt0, d.batt_slope = b0, slope
        truth.add(d.eui, "battery", f"{b0} V falling {-slope * 1000:.0f} mV/day")
    for final in (0.35, 0.45, 0.55, 0.65):
        d = next(it)
        d.loss_final = final
        truth.add(d.eui, "fcnt_gaps", f"loss ramps 0 -> {final:.0%} over the span")
    d = next(it)  # obstruction: 12 dB drop, SF7 -> SF10
    d.snr0, d.drop_at, d.drop_db = 8.0, 3 / 7, 12.0
    truth.add(d.eui, "sf_creep", "obstruction: -12 dB, ADR SF7 -> SF10")
    truth.add(d.eui, "link_drift", "obstruction: -12 dB RSSI")
    d = next(it)  # milder obstruction: SF8 -> SF10, RSSI drop below the drift threshold
    d.snr0, d.drop_at, d.drop_db = 0.0, 3 / 7, 5.0
    truth.add(d.eui, "sf_creep", "obstruction: -5 dB, ADR SF8 -> SF10")
    d = next(it)  # already at SF12, link degrades gradually: ADR cannot help
    d.snr0, d.ramp, d.drop_db = -10.0, (3 / 7, 6 / 7), 8.0
    truth.add(d.eui, "link_margin", "SF12 device losing 8 dB: margin 10 -> 2 dB")
    truth.add(d.eui, "link_drift", "SF12 device losing 8 dB RSSI")
    d = next(it)
    d.stop_at = 3.5 / 7
    truth.add(d.eui, "silent", "stops transmitting after day 3.5")
    d = next(it)
    d.resets_at = (2.3 / 7, 4.1 / 7, 5.6 / 7)
    truth.add(d.eui, "fcnt_reset", "FCnt back to 0 three times")
    d = next(it)  # misconfigured: 48 B at SF12 every 3 min
    d.interval_s, d.snr0, d.app_len = 180, -10.0, 48
    truth.add(d.eui, "duty_cycle", "48 B @ SF12 every 3 min (~1.5 % airtime)")


def simulate(devices: int = 200, gateways: int = 6, days: float = 7, seed: int = 7
             ) -> tuple[list[Uplink], Truth]:
    """Return time-sorted uplinks and the list of injected faults."""
    if devices < 20 or gateways < 3:
        raise ValueError("need at least 20 devices and 3 gateways")
    rng = random.Random(seed)
    truth = Truth()
    gw_ids = [f"9a7e0000{g + 1:08x}" for g in range(gateways)]
    devs = _build_devices(devices, gateways, rng)
    _inject_faults(devs, rng, truth)

    span = timedelta(days=days)
    out_gw = 2
    out_start = START + span * ((4 + 10 / 24) / 7)
    out_end = out_start + 6 * HOURS
    truth.add(gw_ids[out_gw], "gateway_outage", "6 h outage")

    uplinks: list[Uplink] = []
    for d in devs:
        sf, last_step = _adr_sf(d.snr0), START
        fcnt = d.fcnt0
        pending_resets = sorted(d.resets_at)
        t = START + timedelta(seconds=rng.uniform(0, d.interval_s))
        while t < START + span:
            frac = (t - START) / span
            if d.stop_at is not None and frac >= d.stop_at:
                break
            while pending_resets and frac >= pending_resets[0]:
                pending_resets.pop(0)
                fcnt = 0
            drop = 0.0
            if d.drop_at is not None and frac >= d.drop_at:
                drop = d.drop_db
            elif d.ramp:
                drop = d.drop_db * min(1.0, max(0.0, (frac - d.ramp[0]) / (d.ramp[1] - d.ramp[0])))
            snr_nominal = d.snr0 - drop
            if sf < 12 and snr_nominal - DEMOD_FLOOR_DB[sf] < ADR_MARGIN_DB and t - last_step >= 4 * HOURS:
                sf, last_step = sf + 1, t
            wire_fcnt = fcnt % 65536 if d.wrap16 else fcnt
            fcnt += 1
            t_next = t + timedelta(seconds=d.interval_s * rng.uniform(0.97, 1.03))
            heard = []
            routes = [(d.home, 0.0, 1.0)] + [(g, off, 0.75) for g, off in d.secondary]
            for g, off, p in routes:
                if out_start <= t < out_end and g == out_gw:
                    continue
                if rng.random() <= p:
                    snr = snr_nominal - off + rng.gauss(0, 1.0)
                    heard.append(Rx(gw_ids[g], max(-140.0, snr - 117 + rng.gauss(0, 1.5)), snr))
            lost = rng.random() < 0.015 + d.loss_final * frac
            if heard and not lost:
                volts = d.batt0 + d.batt_slope * (t - START).total_seconds() / 86400 + rng.gauss(0, 0.015)
                payload = _payload(volts, 14 + rng.gauss(0, 3), d.app_len)
                battery = int.from_bytes(payload[2:4], "big", signed=True) / 100
                uplinks.append(Uplink(d.eui, t, wire_fcnt, 1, payload, tuple(heard), sf,
                                      battery_v=battery))
            t = t_next
    uplinks.sort(key=lambda u: u.time)
    return uplinks, truth
