from __future__ import annotations

from ..models import Finding, Uplink
from . import battery, duty, fcnt, gateway, link, sf, silent
from .common import Config

CHECKS = (fcnt, link, sf, duty, battery, silent, gateway)


def diagnose(uplinks: list[Uplink], cfg: Config | None = None) -> list[Finding]:
    """Run every check; findings come back unordered (see report.py for ranking)."""
    cfg = cfg or Config()
    findings: list[Finding] = []
    for module in CHECKS:
        findings.extend(module.check(uplinks, cfg))
    return findings


__all__ = ["CHECKS", "Config", "diagnose"]
