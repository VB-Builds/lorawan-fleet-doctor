import random

import pytest

from fleetdoctor.diagnose import duty, gateway, link, sf as sf_check, silent
from fleetdoctor.diagnose import battery
from fleetdoctor.diagnose.common import Config, theil_sen
from conftest import make_uplink

CFG = Config()


def battery_series(start_v: float, slope: float, days: int = 7, noise: float = 0.01, seed: int = 1):
    rng = random.Random(seed)
    return [make_uplink(t_s=i * 3600, fcnt=i,
                        battery=round(start_v + slope * i / 24 + rng.gauss(0, noise), 2))
            for i in range(days * 24)]


def test_theil_sen_ignores_outlier():
    xs = list(range(10))
    ys = [2 * x + 1 for x in xs]
    ys[4] = 100
    assert theil_sen([float(x) for x in xs], [float(y) for y in ys]) == pytest.approx(2.0)


def test_battery_forecast_on_synthetic_line():
    series = battery_series(3.3, -0.05)  # 7 d -> 2.95 V, 9 more days until 2.5 V
    slope, current, days = battery.forecast(series, CFG)
    assert slope == pytest.approx(-0.05, abs=0.005)
    assert days == pytest.approx(9, abs=1.5)
    (f,) = battery.check(series, CFG)
    assert (f.check, f.severity) == ("battery", "critical")
    assert "days until 2.5 V" in f.evidence


def test_battery_healthy_and_short_series_not_flagged():
    assert battery.check(battery_series(3.6, -0.0004), CFG) == []
    assert battery.forecast(battery_series(3.0, -0.1, days=1), CFG) is None
    assert battery.check(battery_series(3.6, 0.0), CFG) == []


def test_battery_warning_band():
    (f,) = battery.check(battery_series(3.4, -0.02), CFG)  # ~3.06 V after 7 d -> ~28 d left
    assert f.severity == "warning"


def test_silent_device():
    live = [make_uplink(dev="live", t_s=i * 3600, fcnt=i) for i in range(100)]
    dead = [make_uplink(dev="dead", t_s=i * 3600, fcnt=i) for i in range(40)]
    (f,) = silent.check(live + dead, CFG)
    assert (f.subject, f.check) == ("dead", "silent")
    assert "60x its usual interval of 60 min" in f.evidence


def test_sf_creep_and_link_drift():
    ups = []
    for i in range(96):  # 4 days hourly: SF7 for two days then SF10, RSSI -12 dB
        late = i >= 48
        ups.append(make_uplink(t_s=i * 3600, fcnt=i, sf=10 if late else 7,
                               rssi=-112 if late else -100, snr=-3 if late else 9))
    (c,) = sf_check.check(ups, CFG)
    assert c.check == "sf_creep" and c.severity == "critical" and "SF7 -> SF10" in c.evidence
    (d,) = link.check(ups, CFG)
    assert d.check == "link_drift" and d.severity == "critical"


def test_link_margin_low():
    ups = [make_uplink(t_s=i * 3600, fcnt=i, sf=12, snr=-19) for i in range(48)]  # +1 dB margin
    (f,) = link.check(ups, CFG)
    assert (f.check, f.severity) == ("link_margin", "warning")


def test_duty_cycle_hog():
    # 61 B frame at SF12 is 2.79 s; one every 3 min is ~1.5 % of the time
    hog = [make_uplink(t_s=i * 180, fcnt=i, sf=12, payload_len=48) for i in range(200)]
    normal = [make_uplink(dev="ok", t_s=i * 1800, fcnt=i, sf=9) for i in range(100)]
    (f,) = duty.check(hog + normal, CFG)
    assert f.severity == "critical" and "limit 1%" in f.evidence


def _gateway_fleet(outage: tuple[int, int] | None):
    ups = []
    for d in range(30):
        home, other = f"gw{d % 3}", f"gw{(d + 1) % 3}"
        for i in range(24 * 4):  # hourly for 4 days
            t = i * 3600 + d * 60
            hour = t // 3600
            down = outage and outage[0] <= hour < outage[1]
            heard = tuple(g for g in (home, other if d % 2 else None) if g and not (down and g == "gw1"))
            if heard:
                ups.append(make_uplink(dev=f"dev{d:02d}", t_s=t, fcnt=i, gws=heard))
    return ups


def test_gateway_outage_detected_with_reroute_counts():
    found = gateway.check(_gateway_fleet((40, 46)), CFG)
    (f,) = found
    assert (f.kind, f.subject, f.check, f.severity) == ("gateway", "gw1", "gateway_outage", "critical")
    assert "6." in f.evidence and "rerouted" in f.evidence
    # 10 home devices + 5 odd-numbered devices that also hear it; the 5 even home devices have no alternative
    assert "15 devices normally reach it: 10 rerouted via another gateway, 5 not heard" in f.evidence


def test_no_gateway_outage_when_healthy():
    assert gateway.check(_gateway_fleet(None), CFG) == []
