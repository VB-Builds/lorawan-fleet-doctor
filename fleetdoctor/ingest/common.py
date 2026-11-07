from __future__ import annotations

import re
from datetime import datetime, timezone


class ParseError(ValueError):
    """The JSON is not a usable LoRa uplink for this format."""


class NotUplink(ParseError):
    """The JSON is a valid event of another type (join, status, ...)."""


_FRAC = re.compile(r"(\.\d{6})\d+")


def parse_time(value: str) -> datetime:
    """ISO-8601 with up to nanosecond fractions (both servers emit them)."""
    value = _FRAC.sub(r"\1", value.strip())
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
