"""ChirpStack v4 integration event `up` (MQTT/HTTP JSON).

Schema: https://www.chirpstack.io/docs/chirpstack/integrations/events.html
"""
from __future__ import annotations

import base64
from typing import Any

from ..models import Rx, Uplink
from .battery import DEFAULT_DECODERS, DecoderRegistry
from .common import NotUplink, ParseError, parse_time


def parse(event: dict[str, Any], decoders: DecoderRegistry = DEFAULT_DECODERS) -> Uplink:
    if "rxInfo" not in event or "txInfo" not in event:
        raise NotUplink("not an `up` event")
    try:
        dev_eui = event["deviceInfo"]["devEui"].lower()
        lora = event["txInfo"]["modulation"]["lora"]
        rx = tuple(
            Rx(r["gatewayId"].lower(), float(r.get("rssi", -140)), float(r.get("snr", 0.0)))
            for r in event["rxInfo"]
        )
        if not rx:
            raise ParseError("no rxInfo entries")
        data = base64.b64decode(event.get("data", ""))
        return Uplink(
            dev_eui=dev_eui,
            time=parse_time(event["time"]),
            # proto3 JSON may omit zero-valued fields
            f_cnt=int(event.get("fCnt", 0)),
            f_port=int(event.get("fPort", 0)),
            payload=data,
            rx=rx,
            sf=int(lora["spreadingFactor"]),
            bw_hz=int(lora["bandwidth"]),
            cr=str(lora.get("codeRate", "CR_4_5")).replace("CR_", "").replace("_", "/"),
            battery_v=decoders.decode(dev_eui, data),
        )
    except ParseError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ParseError(f"bad ChirpStack uplink: {exc!r}") from exc
