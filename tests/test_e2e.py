"""End to end: simulated fleet with injected faults -> parse -> diagnose -> report."""
import json

import pytest

from fleetdoctor import cli, report
from fleetdoctor.diagnose import diagnose
from fleetdoctor.evaluate import score
from fleetdoctor.ingest import iter_uplinks
from fleetdoctor.sim import simulate
from fleetdoctor.sim.render import RENDERERS


@pytest.fixture(scope="module")
def fleet():
    return simulate(devices=200, gateways=6, days=7, seed=7)


def test_every_injected_fault_found_with_few_false_findings(fleet):
    uplinks, truth = fleet
    s = score(diagnose(uplinks), truth)
    assert s.expected == 16
    assert s.recall == 1.0, f"missed {s.missed}"
    assert len(s.false_positives) <= 1, f"false positives {s.false_positives}"
    assert s.precision >= 0.9


@pytest.mark.parametrize("fmt", ["chirpstack", "tts"])
def test_both_wire_formats_give_the_same_diagnosis(fleet, fmt):
    uplinks, truth = fleet
    lines = (json.dumps(RENDERERS[fmt](u)) for u in uplinks)
    parsed = list(iter_uplinks(lines, fmt))
    assert len(parsed) == len(uplinks)
    s = score(diagnose(parsed), truth)
    assert s.recall == 1.0 and s.precision >= 0.9


def test_report_ranks_worst_first_and_lists_gateways(fleet):
    uplinks, truth = fleet
    findings = diagnose(uplinks)
    md = report.to_markdown(uplinks, findings)
    assert md.index("[CRITICAL]") < md.index("[WARNING]")
    assert "## Gateways" in md and md.count("| `9a7e") == 6
    data = json.loads(report.to_json(uplinks, findings))
    assert data["devices"] == 200 and len(data["gateways"]) == 6
    assert sum(g["outages"] for g in data["gateways"]) == 1
    assert {"check", "severity", "evidence", "suggestion"} <= set(data["findings"][0])
    assert any("gateway" in f for f in data["findings"])


def test_cli_roundtrip(tmp_path):
    ev, md = tmp_path / "events.jsonl", tmp_path / "report.md"
    assert cli.main(["simulate", "--out", str(ev), "--format", "tts", "--devices", "60"]) == 0
    assert cli.main(["diagnose", str(ev), "--report", str(md), "--truth", f"{ev}.truth.json"]) == 0
    assert "Top problems" in md.read_text(encoding="utf-8")
