"""Framing and message helpers for the driver <-> helper protocol (v1).

This module has no NVDA dependencies so it can be unit tested directly.
Frame layout: u32 LE length, u8 type, payload. Control payloads are UTF-8
JSON; AUDIO payloads are u16 LE header length, JSON header, raw i16 LE PCM.
"""

import json
import struct

PROTOCOL_VERSION = 1

# Driver -> helper
HELLO = 0x01
SPEAK = 0x02
CANCEL = 0x03
LOAD_VOICE = 0x04
PING = 0x05
SHUTDOWN = 0x06
PLAY_SAMPLE = 0x07
SET_LEXICON = 0x08
# Helper -> driver
AUDIO = 0x81
MARKER = 0x82
DONE = 0x83
ERROR = 0x84
PONG = 0x85
LOG = 0x86

_MAX_FRAME = 32 * 1024 * 1024


def encode_frame(msg_type, payload):
    """Return the bytes for one frame given a type and a bytes payload."""
    return struct.pack("<I", len(payload) + 1) + bytes([msg_type]) + payload


def encode_json(msg_type, obj):
    return encode_frame(msg_type, json.dumps(obj).encode("utf-8"))


def read_frame(read_exactly):
    """Read one frame using a callable read_exactly(n) -> bytes (or None on
    EOF). Returns (msg_type, payload_bytes) or None on EOF."""
    header = read_exactly(4)
    if not header or len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    if length == 0 or length > _MAX_FRAME:
        raise ValueError("bad frame length %d" % length)
    body = read_exactly(length)
    if not body or len(body) < length:
        return None
    return body[0], body[1:]


def parse_audio(payload):
    """Split an AUDIO payload into (header_dict, pcm_bytes)."""
    (hlen,) = struct.unpack("<H", payload[:2])
    header = json.loads(payload[2:2 + hlen])
    pcm = payload[2 + hlen:]
    return header, pcm


def parse_json(payload):
    return json.loads(payload)
