from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from ..models import Uplink
from . import chirpstack, ttn
from .battery import DEFAULT_DECODERS, DecoderRegistry, cayenne_analog_battery
from .common import NotUplink, ParseError

FORMATS: dict[str, Callable[..., Uplink]] = {"chirpstack": chirpstack.parse, "tts": ttn.parse}


def parse_event(event: dict[str, Any], fmt: str = "auto",
                decoders: DecoderRegistry = DEFAULT_DECODERS) -> Uplink:
    if fmt == "auto":
        fmt = "tts" if "end_device_ids" in event else "chirpstack"
    return FORMATS[fmt](event, decoders)


def iter_uplinks(lines: Iterable[str], fmt: str = "auto",
                 decoders: DecoderRegistry = DEFAULT_DECODERS) -> Iterator[Uplink]:
    """Yield uplinks from JSON lines; non-uplink events and malformed lines are skipped."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            yield parse_event(json.loads(line), fmt, decoders)
        except (ParseError, json.JSONDecodeError):
            continue


def load_file(path: str | Path, fmt: str = "auto",
              decoders: DecoderRegistry = DEFAULT_DECODERS) -> list[Uplink]:
    with open(path, encoding="utf-8") as fh:
        return list(iter_uplinks(fh, fmt, decoders))


__all__ = ["DecoderRegistry", "FORMATS", "NotUplink", "ParseError", "cayenne_analog_battery",
           "iter_uplinks", "load_file", "parse_event"]
