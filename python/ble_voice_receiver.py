#!/usr/bin/env python3
"""
BLE Voice Receiver for Optidex

Connects to ESP32-S3 BLE peripheral (optidex-voice), subscribes to notifications,
reassembles streamed PCM16 frames into a WAV file, and prints JSON events to stdout.

This is used by Optidex Node process as a subprocess.
"""

import asyncio
import json
import os
import struct
import sys
import time
from dataclasses import dataclass
from typing import Optional

from bleak import BleakClient, BleakScanner


SERVICE_UUID = "f4f16c20-1f3b-4c56-a5d7-6c5c2e1b8a10"
NOTIFY_CHAR_UUID = "f4f16c21-1f3b-4c56-a5d7-6c5c2e1b8a10"
CONTROL_CHAR_UUID = "f4f16c22-1f3b-4c56-a5d7-6c5c2e1b8a10"


def _wav_header(num_samples: int, sample_rate: int, channels: int, bits: int = 16) -> bytes:
    # PCM RIFF header
    byte_rate = sample_rate * channels * (bits // 8)
    block_align = channels * (bits // 8)
    data_size = num_samples * channels * (bits // 8)
    riff_size = 36 + data_size
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_size,
    )


@dataclass
class Session:
    session_id: int
    sample_rate: int
    channels: int
    frame_samples: int
    pcm_bytes: bytearray
    last_seq: int = 0
    start_ts: float = 0.0


def parse_packet(data: bytes):
    if len(data) < 16:
        return None
    if data[0:4] != b"VOIC":
        return None
    pkt_type = data[4]
    payload_len = struct.unpack_from("<H", data, 6)[0]
    session_id = struct.unpack_from("<I", data, 8)[0]
    seq = struct.unpack_from("<I", data, 12)[0]
    payload = data[16 : 16 + payload_len]
    return pkt_type, session_id, seq, payload


async def find_device(name: str) -> Optional[str]:
    # Prefer service UUID match; also allow name match.
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        if d.name == name:
            return d.address
    # fallback: look for advertised service uuid when available
    for d in devices:
        uuids = []
        try:
            uuids = (d.metadata or {}).get("uuids") or []
        except Exception:
            uuids = []
        if any(u.lower() == SERVICE_UUID.lower() for u in uuids):
            return d.address
    return None


async def run(device_name: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    while True:
        addr = await find_device(device_name)
        if not addr:
            print(json.dumps({"event": "status", "status": "scan_no_device"}), flush=True)
            await asyncio.sleep(2.0)
            continue

        print(json.dumps({"event": "status", "status": "connecting", "address": addr}), flush=True)

        session: Optional[Session] = None

        def on_notify(_sender: int, data: bytearray):
            nonlocal session
            parsed = parse_packet(bytes(data))
            if not parsed:
                return

            pkt_type, sid, seq, payload = parsed

            if pkt_type == 3:  # ping
                return

            if pkt_type == 0:  # start
                if len(payload) < 8:
                    return
                sample_rate = struct.unpack_from("<I", payload, 0)[0]
                channels = struct.unpack_from("<H", payload, 4)[0]
                frame_samples = struct.unpack_from("<H", payload, 6)[0]
                session = Session(
                    session_id=sid,
                    sample_rate=sample_rate,
                    channels=channels,
                    frame_samples=frame_samples,
                    pcm_bytes=bytearray(),
                    last_seq=0,
                    start_ts=time.time(),
                )
                print(
                    json.dumps(
                        {
                            "event": "start",
                            "session_id": sid,
                            "sample_rate": sample_rate,
                            "channels": channels,
                            "frame_samples": frame_samples,
                        }
                    ),
                    flush=True,
                )
                return

            if pkt_type == 1:  # pcm
                if not session or session.session_id != sid:
                    return
                # Best-effort sequence tracking (BLE can drop notifications)
                session.last_seq = max(session.last_seq, seq)
                session.pcm_bytes.extend(payload)
                return

            if pkt_type == 2:  # end
                if not session or session.session_id != sid:
                    return
                reason = payload[0] if payload else 255

                pcm = bytes(session.pcm_bytes)
                # Determine sample count
                bytes_per_sample = 2 * session.channels
                num_samples = len(pcm) // bytes_per_sample

                ts_ms = int(time.time() * 1000)
                wav_path = os.path.join(out_dir, f"esp32-voice-{sid}-{ts_ms}.wav")
                with open(wav_path, "wb") as f:
                    f.write(_wav_header(num_samples, session.sample_rate, session.channels, 16))
                    f.write(pcm[: num_samples * bytes_per_sample])

                dur_ms = int((time.time() - session.start_ts) * 1000)
                print(
                    json.dumps(
                        {
                            "event": "utterance",
                            "session_id": sid,
                            "path": wav_path,
                            "reason": reason,
                            "duration_ms": dur_ms,
                            "bytes": len(pcm),
                        }
                    ),
                    flush=True,
                )
                session = None

        try:
            async with BleakClient(addr) as client:
                print(
                    json.dumps(
                        {
                            "event": "status",
                            "status": "connected",
                            "address": addr,
                            "mtu": getattr(client, "mtu_size", None),
                        }
                    ),
                    flush=True,
                )

                # Subscribe
                await client.start_notify(NOTIFY_CHAR_UUID, on_notify)

                # Keep alive
                while client.is_connected:
                    await asyncio.sleep(1.0)

        except Exception as e:
            print(json.dumps({"event": "status", "status": "error", "error": str(e)}), flush=True)
            await asyncio.sleep(1.0)


def main():
    device_name = os.environ.get("ESP32_VOICE_BLE_NAME") or "optidex-voice"
    out_dir = os.environ.get("ESP32_VOICE_OUT_DIR") or "/home/dash/optidex/data/recordings"

    if len(sys.argv) > 1:
        device_name = sys.argv[1]
    if len(sys.argv) > 2:
        out_dir = sys.argv[2]

    asyncio.run(run(device_name, out_dir))


if __name__ == "__main__":
    main()


