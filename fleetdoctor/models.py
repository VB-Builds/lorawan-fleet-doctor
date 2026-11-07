"""Core data types shared by ingest, diagnose and report."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Severity = Literal["critical", "warning"]


@dataclass(frozen=True)
class Rx:
    """One gateway's reception of an uplink."""

    gateway_id: str
    rssi: float
    snr: float


@dataclass(frozen=True)
class Uplink:
    """Network-server-neutral view of one uplink frame."""

    dev_eui: str
    time: datetime
    f_cnt: int
    f_port: int
    payload: bytes
    rx: tuple[Rx, ...]
    sf: int
    bw_hz: int = 125_000
    cr: str = "4/5"
    battery_v: float | None = None

    @property
    def best(self) -> Rx:
        return max(self.rx, key=lambda r: r.rssi)

    @property
    def phy_len(self) -> int:
        """LoRaWAN PHY payload: MHDR + FHDR + FPort + MIC overhead is 13 bytes."""
        return len(self.payload) + 13


@dataclass(frozen=True)
class Finding:
    subject: str
    check: str
    severity: Severity
    evidence: str
    suggestion: str
    kind: Literal["device", "gateway"] = "device"

    def to_dict(self) -> dict[str, str]:
        return {
            self.kind: self.subject,
            "check": self.check,
            "severity": self.severity,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }
