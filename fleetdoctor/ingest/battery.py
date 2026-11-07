"""Pluggable battery decoding: payload bytes -> battery voltage (V)."""
from __future__ import annotations

from typing import Callable, Mapping

BatteryDecoder = Callable[[bytes], "float | None"]

# Cayenne LPP data type -> data size in bytes (enough to skip over other fields).
_LPP_SIZES = {0x00: 1, 0x01: 1, 0x02: 2, 0x03: 2, 0x65: 2, 0x66: 1, 0x67: 2,
              0x68: 1, 0x71: 6, 0x73: 2, 0x86: 6, 0x88: 9}
_LPP_ANALOG_IN = 0x02


def cayenne_analog_battery(channel: int = 1) -> BatteryDecoder:
    """Read the Cayenne LPP analog-input value (signed 16 bit, 0.01 steps) on `channel`."""

    def decode(data: bytes) -> float | None:
        i = 0
        while i + 2 <= len(data):
            ch, typ = data[i], data[i + 1]
            size = _LPP_SIZES.get(typ)
            if size is None or i + 2 + size > len(data):
                return None
            if ch == channel and typ == _LPP_ANALOG_IN:
                return int.from_bytes(data[i + 2 : i + 4], "big", signed=True) / 100
            i += 2 + size
        return None

    return decode


class DecoderRegistry:
    """Per-device decoders with a default; devices without a match yield no battery data."""

    def __init__(self, default: BatteryDecoder | None = None,
                 per_device: Mapping[str, BatteryDecoder] | None = None) -> None:
        self.default = default
        self.per_device = dict(per_device or {})

    def decode(self, dev_eui: str, data: bytes) -> float | None:
        decoder = self.per_device.get(dev_eui, self.default)
        return decoder(data) if decoder and data else None


DEFAULT_DECODERS = DecoderRegistry(default=cayenne_analog_battery(1))
