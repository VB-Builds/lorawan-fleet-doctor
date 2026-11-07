import json
from pathlib import Path

import pytest

from fleetdoctor.ingest import NotUplink, ParseError, cayenne_analog_battery, iter_uplinks, parse_event
from fleetdoctor.ingest.battery import DecoderRegistry
from fleetdoctor.sim.render import to_chirpstack, to_tts
from conftest import make_uplink

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


@pytest.mark.parametrize("name,fmt", [("chirpstack_up.json", "chirpstack"), ("tts_up.json", "tts")])
def test_both_formats_normalise_identically(name, fmt):
    u = parse_event(load(name), fmt)
    assert u.dev_eui == "d3b00000000000aa"
    assert (u.f_cnt, u.f_port, u.sf, u.bw_hz, u.cr) == (1234, 1, 9, 125_000, "4/5")
    assert u.time.isoformat() == "2026-03-02T08:15:30.123456+00:00" or u.time.microsecond == 130456
    assert [(r.gateway_id.removeprefix("eui-"), r.rssi, r.snr) for r in u.rx] == [
        ("9a7e000000000001", -112, 4.5), ("9a7e000000000004", -121, -1.2)]
    assert u.best.gateway_id.endswith("0001")
    assert u.battery_v == 3.70  # Cayenne analog ch1 = 0x0172 / 100
    assert u.phy_len == 8 + 13


def test_auto_detect_and_skip_non_uplinks():
    lines = [json.dumps(load("chirpstack_up.json")), json.dumps(load("tts_up.json")),
             json.dumps({"deviceInfo": {"devEui": "01"}, "devAddr": "00189440"}),  # join event
             "not json", ""]
    assert len(list(iter_uplinks(lines))) == 2


def test_non_uplink_and_malformed_raise():
    with pytest.raises(NotUplink):
        parse_event({"deviceInfo": {"devEui": "01"}}, "chirpstack")
    with pytest.raises(ParseError):
        bad = load("tts_up.json")
        del bad["uplink_message"]["settings"]
        parse_event(bad, "tts")


def test_zero_valued_fields_omitted_by_server():
    ev = load("tts_up.json")
    del ev["uplink_message"]["f_cnt"]
    assert parse_event(ev, "tts").f_cnt == 0


def test_render_parse_roundtrip_both_formats():
    u = make_uplink(fcnt=77, sf=10, gws=("9a7e000000000001", "9a7e000000000002"), rssi=-117, snr=-3.5)
    for render, fmt in ((to_chirpstack, "chirpstack"), (to_tts, "tts")):
        back = parse_event(json.loads(json.dumps(render(u))), fmt)
        assert (back.dev_eui, back.f_cnt, back.sf, back.time) == (u.dev_eui, 77, 10, u.time)
        assert [r.snr for r in back.rx] == [-3.5, -3.5]


def test_cayenne_decoder():
    dec = cayenne_analog_battery(1)
    assert dec(bytes([1, 0x02, 0x01, 0x72])) == 3.70
    assert dec(bytes([2, 0x67, 0, 230, 1, 0x02, 0x01, 0x2C])) == 3.0  # skips temperature
    assert dec(bytes([2, 0x02, 0x01, 0x72])) is None  # other channel
    assert dec(bytes([1, 0x99, 0, 0])) is None  # unknown type: stop, don't guess
    assert cayenne_analog_battery(3)(bytes([3, 0x02, 0xFF, 0x9C])) == -1.0  # signed


def test_per_device_decoder_hook():
    reg = DecoderRegistry(per_device={"aa": lambda data: data[0] / 10})
    assert reg.decode("aa", b"\x25") == 3.7
    assert reg.decode("bb", b"\x25") is None
