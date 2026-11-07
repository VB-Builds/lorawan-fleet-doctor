"""LoRa time-on-air, Semtech SX127x datasheet / AN1200.13 formula."""
from __future__ import annotations

from math import ceil

from ..models import Uplink

# Typical demodulation floor SNR (dB) per spreading factor (SX1276 datasheet, table "LoRa SNR").
DEMOD_FLOOR_DB = {7: -7.5, 8: -10.0, 9: -12.5, 10: -15.0, 11: -17.5, 12: -20.0}


def time_on_air(payload_len: int, sf: int, bw_hz: int = 125_000, cr: str = "4/5",
                preamble: int = 8, explicit_header: bool = True, crc: bool = True,
                low_data_rate: bool | None = None) -> float:
    """Seconds on air for a PHY payload of `payload_len` bytes (SF7..SF12).

    `low_data_rate=None` applies the Semtech rule: optimise when the symbol time exceeds 16 ms.
    """
    if sf not in DEMOD_FLOOR_DB:
        raise ValueError(f"SF{sf} not supported (7..12)")
    cr_index = int(cr.split("/")[1]) - 4  # 4/5 -> 1 ... 4/8 -> 4
    if not 1 <= cr_index <= 4:
        raise ValueError(f"bad coding rate {cr!r}")
    t_sym = (2 ** sf) / bw_hz
    de = int(t_sym > 0.016 if low_data_rate is None else low_data_rate)
    ih = int(not explicit_header)
    numerator = 8 * payload_len - 4 * sf + 28 + 16 * int(crc) - 20 * ih
    n_payload = 8 + max(ceil(numerator / (4 * (sf - 2 * de))) * (cr_index + 4), 0)
    return (preamble + 4.25 + n_payload) * t_sym


def uplink_airtime(u: Uplink) -> float:
    return time_on_air(u.phy_len, u.sf, u.bw_hz, u.cr)


def snr_margin(snr: float, sf: int) -> float:
    """dB above the demodulation floor of this spreading factor."""
    return snr - DEMOD_FLOOR_DB[sf]
