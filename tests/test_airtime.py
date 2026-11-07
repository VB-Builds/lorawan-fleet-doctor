"""Time-on-air checked against the published LoRaWAN airtime calculator at
https://www.thethingsnetwork.org/airtime-calculator (EU868, 10 B application payload = 23 B PHY
payload, 8-symbol preamble, explicit header, CRC on, CR 4/5, 125 kHz) and against hand
calculation of the Semtech formula (SX1276 datasheet / AN1200.13).
"""
import pytest

from fleetdoctor.diagnose.airtime import snr_margin, time_on_air


@pytest.mark.parametrize("sf,ms", [(7, 61.7), (8, 113.2), (9, 205.8), (10, 370.7), (11, 823.3),
                                   (12, 1482.8)])
def test_matches_published_calculator(sf, ms):
    assert time_on_air(23, sf) * 1000 == pytest.approx(ms, abs=0.06)


def test_hand_calculated_sf7_10_bytes():
    # Tsym = 128/125000 = 1.024 ms; payload symbols = 8 + ceil((80-28+28+16)/28)*5 = 28
    # preamble = 12.25 symbols -> 40.25 symbols = 41.216 ms
    assert time_on_air(10, 7) == pytest.approx(0.041216)


def test_max_sf12_frame_and_other_options():
    assert time_on_air(64, 12) == pytest.approx(2.7935, abs=1e-4)  # 51 B payload + 13 B overhead
    assert time_on_air(23, 7, bw_hz=250_000) == pytest.approx(0.030848)  # DR6
    assert time_on_air(23, 7, cr="4/8") > time_on_air(23, 7)
    assert time_on_air(23, 7, crc=False) < time_on_air(23, 7)
    assert time_on_air(23, 12, low_data_rate=False) < time_on_air(23, 12)  # LDRO costs airtime


def test_ldro_auto_only_when_symbol_over_16ms():
    assert time_on_air(20, 10) == time_on_air(20, 10, low_data_rate=False)  # 8.2 ms symbol
    assert time_on_air(20, 11) == time_on_air(20, 11, low_data_rate=True)  # 16.4 ms symbol


def test_invalid_inputs():
    with pytest.raises(ValueError):
        time_on_air(10, 6)
    with pytest.raises(ValueError):
        time_on_air(10, 7, cr="4/9")


def test_margin_vs_floor():
    assert snr_margin(-10, 10) == 5.0
    assert snr_margin(-8, 7) == -0.5
