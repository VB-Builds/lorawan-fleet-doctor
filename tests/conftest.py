from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fleetdoctor.models import Rx, Uplink

T0 = datetime(2026, 3, 2, tzinfo=timezone.utc)


def make_uplink(dev: str = "d3b000000000000a", t_s: float = 0, fcnt: int = 0, sf: int = 7,
                gws: tuple[str, ...] = ("gw1",), rssi: float = -100, snr: float = 5,
                battery: float | None = None, payload_len: int = 8) -> Uplink:
    return Uplink(dev, T0 + timedelta(seconds=t_s), fcnt, 1, bytes(payload_len),
                  tuple(Rx(g, rssi, snr) for g in gws), sf, battery_v=battery)
