"""Frame-counter analysis: missed uplinks, 16/32-bit rollover, resets."""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Finding, Uplink
from .common import Config, by_device, fmt_span

MAX_PLAUSIBLE_GAP = 2000  # larger forward jumps are treated as unknown, not as loss
_WRAP16, _WRAP32 = 1 << 16, 1 << 32


@dataclass(frozen=True)
class FcntStats:
    received: int
    missed: int
    resets: int
    rollovers: int

    @property
    def expected(self) -> int:
        return self.received + self.missed

    @property
    def loss(self) -> float:
        return self.missed / self.expected if self.expected else 0.0


def analyze(fcnts: list[int]) -> FcntStats:
    """Walk frame counters in arrival order.

    A decrease is a rollover when the previous value was within MAX_PLAUSIBLE_GAP of the
    16- or 32-bit limit and the wrapped distance is plausible; otherwise it is a reset
    (reboot / rejoin) and no loss is counted across it.
    """
    received = missed = resets = rollovers = 0
    prev: int | None = None
    for cur in fcnts:
        if prev is None:
            received += 1
        elif cur == prev:
            pass  # duplicate delivery
        elif cur > prev:
            received += 1
            if cur - prev - 1 <= MAX_PLAUSIBLE_GAP:
                missed += cur - prev - 1
        else:
            received += 1
            for wrap in (_WRAP16, _WRAP32):
                gap = cur + wrap - prev - 1
                if prev < wrap and gap <= MAX_PLAUSIBLE_GAP and wrap - prev <= MAX_PLAUSIBLE_GAP:
                    rollovers += 1
                    missed += gap
                    break
            else:
                resets += 1
        prev = cur
    return FcntStats(received, missed, resets, rollovers)


def check(uplinks: list[Uplink], cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    for eui, series in by_device(uplinks).items():
        if len(series) < cfg.min_uplinks:
            continue
        stats = analyze([u.f_cnt for u in series])
        span = fmt_span(series[0].time, series[-1].time)
        if stats.loss >= cfg.loss_warn:
            half = len(series) // 2
            first, last = analyze([u.f_cnt for u in series[:half]]), analyze([u.f_cnt for u in series[half:]])
            trend = (f"; loss grew from {first.loss:.0%} to {last.loss:.0%} (first vs second half)"
                     if last.loss > first.loss + 0.05 else "")
            findings.append(Finding(
                eui, "fcnt_gaps", "critical" if stats.loss >= cfg.loss_crit else "warning",
                f"FCnt gaps: {stats.missed} of {stats.expected} expected uplinks missing "
                f"({stats.loss:.0%}) over {span}{trend}",
                "Check antenna/placement and nearby interference; consider a closer gateway "
                "or a lower data rate (higher SF) if margin is thin."))
        if stats.resets:
            findings.append(Finding(
                eui, "fcnt_reset", "critical" if stats.resets >= cfg.reset_crit else "warning",
                f"Frame counter went backwards {stats.resets}x over {span} "
                "(device reboot or rejoin)",
                "Look for brown-outs, watchdog resets or firmware crashes; repeated resets "
                "often precede battery failure."))
    return findings
