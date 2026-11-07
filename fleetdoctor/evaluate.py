"""Score findings against the simulator's injected-fault list."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Finding
from .sim.fleet import Truth


def _norm(subject: str) -> str:
    return subject.lower().removeprefix("eui-")  # TTS gateway ids carry an "eui-" prefix


@dataclass(frozen=True)
class Score:
    true_positives: int
    expected: int
    reported: int
    missed: tuple[tuple[str, str], ...]
    false_positives: tuple[tuple[str, str], ...]

    @property
    def precision(self) -> float:
        return self.true_positives / self.reported if self.reported else 1.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.expected if self.expected else 1.0

    def summary(self) -> str:
        return (f"precision {self.precision:.1%} ({self.true_positives}/{self.reported}), "
                f"recall {self.recall:.1%} ({self.true_positives}/{self.expected})")


def score(findings: list[Finding], truth: Truth) -> Score:
    """A finding counts once per (subject, check); anything not injected is a false positive."""
    expected = {(_norm(s), c) for s, c in truth.pairs()}
    reported = {(_norm(f.subject), f.check) for f in findings}
    return Score(len(expected & reported), len(expected), len(reported),
                 tuple(sorted(expected - reported)), tuple(sorted(reported - expected)))
