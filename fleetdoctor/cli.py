"""Command line: simulate | diagnose | listen."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

from . import ingest, report
from .diagnose import diagnose
from .evaluate import score
from .ingest.common import ParseError
from .models import Uplink
from .sim import Truth, simulate, write_events

FORMATS = ["chirpstack", "tts"]


def cmd_simulate(a: argparse.Namespace) -> int:
    uplinks, truth = simulate(a.devices, a.gateways, a.days, a.seed)
    write_events(uplinks, a.out, a.format)
    truth_path = Path(str(a.out) + ".truth.json")
    truth.save(truth_path)
    print(f"{len(uplinks)} {a.format} events -> {a.out}; injected faults -> {truth_path}")
    return 0


def cmd_diagnose(a: argparse.Namespace) -> int:
    uplinks = ingest.load_file(a.events, a.format)
    if not uplinks:
        print("no usable uplink events found (check --format)", file=sys.stderr)
        return 2
    findings = diagnose(uplinks)
    if a.report:
        Path(a.report).write_text(report.to_markdown(uplinks, findings), encoding="utf-8")
    if a.json:
        Path(a.json).write_text(report.to_json(uplinks, findings), encoding="utf-8")
    if not a.report and not a.json:
        print(report.to_markdown(uplinks, findings))
    ranked = report.rank(findings)
    print(f"{len(uplinks)} uplinks, {len(findings)} findings "
          f"({sum(f.severity == 'critical' for f in ranked)} critical)")
    if a.truth:
        s = score(findings, Truth.load(a.truth))
        print("vs injected faults:", s.summary())
        for pair in s.missed:
            print("  missed:", pair)
        for pair in s.false_positives:
            print("  false positive:", pair)
    return 0


def cmd_listen(a: argparse.Namespace) -> int:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("listen needs paho-mqtt: pip install paho-mqtt", file=sys.stderr)
        return 2
    window: deque[Uplink] = deque()

    def on_message(_c: object, _u: object, msg: "mqtt.MQTTMessage") -> None:
        try:
            up = ingest.parse_event(json.loads(msg.payload), a.format)
        except (ParseError, ValueError):
            return
        window.append(up)
        while window and (up.time - window[0].time).days >= a.window_days:
            window.popleft()

    client = (mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, "CallbackAPIVersion")
              else mqtt.Client())
    client.on_message = on_message
    client.connect(a.mqtt, a.port)
    client.subscribe(a.topic)
    client.loop_start()
    print(f"listening on {a.mqtt}:{a.port} {a.topic}; diagnosing every {a.every}s (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(a.every)
            ups = list(window)
            if len(ups) < 50:
                print(f"{len(ups)} uplinks buffered, waiting for more data")
                continue
            findings = diagnose(ups)
            text = report.to_markdown(ups, findings)
            if a.report:
                Path(a.report).write_text(text, encoding="utf-8")
            else:
                print(text)
    except KeyboardInterrupt:
        client.loop_stop()
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fleetdoctor", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="write a simulated fleet with injected faults")
    s.add_argument("--devices", type=int, default=200)
    s.add_argument("--gateways", type=int, default=6)
    s.add_argument("--days", type=float, default=7)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--out", default="events.jsonl")
    s.add_argument("--format", choices=FORMATS, default="chirpstack")
    s.set_defaults(fn=cmd_simulate)

    d = sub.add_parser("diagnose", help="diagnose a JSON-lines file of uplink events")
    d.add_argument("events")
    d.add_argument("--format", choices=[*FORMATS, "auto"], default="auto")
    d.add_argument("--report", help="write Markdown report here")
    d.add_argument("--json", help="write JSON report here")
    d.add_argument("--truth", help="score against a simulator .truth.json")
    d.set_defaults(fn=cmd_diagnose)

    li = sub.add_parser("listen", help="live mode over MQTT (needs paho-mqtt)")
    li.add_argument("--mqtt", required=True, help="broker host")
    li.add_argument("--port", type=int, default=1883)
    li.add_argument("--topic", default="application/+/device/+/event/up")
    li.add_argument("--format", choices=[*FORMATS, "auto"], default="chirpstack")
    li.add_argument("--every", type=int, default=300, help="seconds between diagnoses")
    li.add_argument("--window-days", type=int, default=7)
    li.add_argument("--report", help="rewrite this Markdown file each cycle")
    li.set_defaults(fn=cmd_listen)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
