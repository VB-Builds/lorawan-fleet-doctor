from __future__ import annotations

import json
from pathlib import Path

from ..models import Uplink
from .fleet import Truth, simulate
from .render import RENDERERS


def write_events(uplinks: list[Uplink], path: str | Path, fmt: str = "chirpstack") -> None:
    render = RENDERERS[fmt]
    with open(path, "w", encoding="utf-8") as fh:
        for u in uplinks:
            fh.write(json.dumps(render(u), separators=(",", ":")) + "\n")


__all__ = ["RENDERERS", "Truth", "simulate", "write_events"]
