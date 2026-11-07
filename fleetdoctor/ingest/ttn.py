"""The Things Stack v3 uplink message (webhook / MQTT `.../up`).

Data formats: https://www.thethingsindustries.com/docs/the-things-stack/concepts/data-formats/
Message types: https://www.thethingsindustries.com/docs/api/reference/grpc/
"""
from __future__ import annotations

import base64
from typing import Any

from ..models import Rx, Uplink
from .battery import DEFAULT_DECODERS, DecoderRegistry
from .common import NotUplink, ParseError, parse_time


def parse(event: dict[str, Any], decoders: DecoderRegistry = DEFAULT_DECODERS) -> Uplink:
    msg = event.get("uplink_message")
    if msg is None:
        raise NotUplink("no uplink_message")
    try:
        dev_eui = event["end_device_ids"]["dev_eui"].lower()
        lora = msg["settings"]["data_rate"]["lora"]
        rx = tuple(
            Rx(m["gateway_ids"]["gateway_id"].lower(), float(m.get("rssi", -140)),
               float(m.get("snr", 0.0)))
            for m in msg["rx_metadata"]
        )
        if not rx:
            raise ParseError("no rx_metadata entries")
        data = base64.b64decode(msg.get("frm_payload", ""))
        return Uplink(
            dev_eui=dev_eui,
            time=parse_time(event.get("received_at") or msg["received_at"]),
            # f_cnt and f_port are omitted by the server when zero
            f_cnt=int(msg.get("f_cnt", 0)),
            f_port=int(msg.get("f_port", 0)),
            payload=data,
            rx=rx,
            sf=int(lora["spreading_factor"]),
            bw_hz=int(lora["bandwidth"]),
            cr=str(lora.get("coding_rate", "4/5")),
            battery_v=decoders.decode(dev_eui, data),
        )
    except ParseError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ParseError(f"bad TTS uplink: {exc!r}") from exc
