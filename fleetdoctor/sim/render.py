"""Render an `Uplink` back into ChirpStack v4 / The Things Stack v3 JSON (inverse of ingest)."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Any

from ..models import Uplink


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="microseconds")


def _dev_addr(eui: str) -> str:
    return eui[-8:]


def to_chirpstack(u: Uplink) -> dict[str, Any]:
    ns = uuid.uuid5(uuid.NAMESPACE_URL, f"{u.dev_eui}/{u.f_cnt}/{u.time.isoformat()}")
    return {
        "deduplicationId": str(ns),
        "time": _iso(u.time),
        "deviceInfo": {
            "tenantId": "00000000-0000-4000-8000-000000000001",
            "tenantName": "demo",
            "applicationId": "00000000-0000-4000-8000-000000000002",
            "applicationName": "fleet-demo",
            "deviceProfileId": "00000000-0000-4000-8000-000000000003",
            "deviceProfileName": "class-a-eu868",
            "deviceName": f"sensor-{u.dev_eui[-4:]}",
            "devEui": u.dev_eui,
        },
        "devAddr": _dev_addr(u.dev_eui),
        "adr": True,
        "dr": 12 - u.sf if u.bw_hz == 125_000 else 5,
        "fCnt": u.f_cnt,
        "fPort": u.f_port,
        "confirmed": False,
        "data": base64.b64encode(u.payload).decode(),
        "rxInfo": [
            {"gatewayId": r.gateway_id, "uplinkId": i + 1, "rssi": round(r.rssi),
             "snr": round(r.snr, 1), "channel": 0, "rfChain": 0, "context": "AAAAAA==",
             "crcStatus": "CRC_OK"}
            for i, r in enumerate(u.rx)
        ],
        "txInfo": {
            "frequency": 868_100_000,
            "modulation": {"lora": {"bandwidth": u.bw_hz, "spreadingFactor": u.sf,
                                     "codeRate": "CR_" + u.cr.replace("/", "_")}},
        },
    }


def to_tts(u: Uplink) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "session_key_id": "AAAAAAAAAAAAAAAAAAAAAA==",
        "frm_payload": base64.b64encode(u.payload).decode(),
        "rx_metadata": [
            {"gateway_ids": {"gateway_id": f"eui-{r.gateway_id}", "eui": r.gateway_id.upper()},
             "time": _iso(u.time), "rssi": round(r.rssi), "channel_rssi": round(r.rssi),
             "snr": round(r.snr, 1), "channel_index": 0}
            for r in u.rx
        ],
        "settings": {
            "data_rate": {"lora": {"bandwidth": u.bw_hz, "spreading_factor": u.sf,
                                   "coding_rate": u.cr}},
            "frequency": "868100000",
        },
        "received_at": _iso(u.time),
    }
    if u.f_cnt:  # the server omits zero-valued fields
        msg["f_cnt"] = u.f_cnt
    if u.f_port:
        msg["f_port"] = u.f_port
    return {
        "end_device_ids": {
            "device_id": f"sensor-{u.dev_eui[-4:]}",
            "application_ids": {"application_id": "fleet-demo"},
            "dev_eui": u.dev_eui.upper(),
            "join_eui": "0000000000000000",
            "dev_addr": _dev_addr(u.dev_eui).upper(),
        },
        "correlation_ids": [f"as:up:{u.dev_eui}-{u.f_cnt}"],
        "received_at": _iso(u.time),
        "uplink_message": msg,
    }


RENDERERS = {"chirpstack": to_chirpstack, "tts": to_tts}
