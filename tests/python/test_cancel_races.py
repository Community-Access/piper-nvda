"""Cancelled speech must stay cancelled.

Two layers guard it: the driver drops frames whose utteranceId was cancelled
(frames still in the pipe when CANCEL was sent), and the audio pump's
generation counter makes the feeder drop items that raced the cancel drain.
"""

import json
import struct
import threading
import time

import synthDrivers.piper as piper
from synthDrivers.piper import _audio, _protocol as proto


def _audio_payload(uid, pcm):
    header = json.dumps({"utteranceId": uid, "seq": 0}).encode()
    return struct.pack("<H", len(header)) + header + pcm


def _json_payload(obj):
    return json.dumps(obj).encode()


# -- driver-level filtering -------------------------------------------------

class RecordingPump:
    def __init__(self):
        self.frames = []

    def handle_frame(self, msg_type, payload):
        self.frames.append(msg_type)


def _driver_with_pump():
    d = piper.SynthDriver.__new__(piper.SynthDriver)
    d._pump = RecordingPump()
    d._cancelled_upto = 0
    return d


def test_frames_from_cancelled_utterances_are_dropped():
    d = _driver_with_pump()
    d._cancelled_upto = 3
    d._on_frame(proto.AUDIO, _audio_payload(3, b"\x00\x00"))
    d._on_frame(proto.MARKER, _json_payload({"utteranceId": 3, "index": 5}))
    d._on_frame(proto.DONE, _json_payload({"utteranceId": 2}))
    assert d._pump.frames == []


def test_frames_from_the_current_utterance_pass():
    d = _driver_with_pump()
    d._cancelled_upto = 3
    d._on_frame(proto.AUDIO, _audio_payload(4, b"\x00\x00"))
    d._on_frame(proto.MARKER, _json_payload({"utteranceId": 4, "index": 1}))
    d._on_frame(proto.DONE, _json_payload({"utteranceId": 4}))
    assert d._pump.frames == [proto.AUDIO, proto.MARKER, proto.DONE]


# -- pump-level generation handling ----------------------------------------

class FakePlayer:
    def __init__(self):
        self.fed = []
        self.stops = 0
        self.idles = 0

    def feed(self, data, onDone=None):
        self.fed.append(bytes(data))
        if onDone is not None:
            onDone()

    def stop(self):
        self.stops += 1

    def idle(self):
        self.idles += 1


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_item_that_raced_the_cancel_drain_is_dropped():
    player = FakePlayer()
    done = []
    pump = _audio.AudioPump(player, lambda i: None, lambda: done.append(1))
    try:
        pump.cancel()
        # An item from before the cancel that the drain missed (or that the
        # feeder already held): tagged with the old generation.
        pump._q.put(("audio", pump._gen - 1, b"STALE"))
        # The next utterance arrives normally.
        pump.handle_frame(proto.AUDIO, _audio_payload(2, b"FRESH"))
        pump.handle_frame(proto.DONE, _json_payload({"utteranceId": 2}))
        assert _wait_for(lambda: done)
        assert player.fed == [b"FRESH"]
    finally:
        pump.shutdown()


def test_reset_discards_audio_a_stale_item_buffered():
    player = FakePlayer()
    done = []
    pump = _audio.AudioPump(player, lambda i: None, lambda: done.append(1))
    try:
        # Simulate the worst interleaving: stale audio was appended to the
        # buffer with the current generation just before cancel() bumped it.
        pump._q.put(("audio", pump._gen, b"STALE"))
        # Give the feeder a moment; whether it buffered the item or the
        # cancel drain catches it, the outcome below must be the same.
        time.sleep(0.05)
        pump.cancel()  # bumps generation and enqueues the reset
        pump.handle_frame(proto.AUDIO, _audio_payload(2, b"FRESH"))
        pump.handle_frame(proto.DONE, _json_payload({"utteranceId": 2}))
        assert _wait_for(lambda: done)
        assert player.fed == [b"FRESH"]
    finally:
        pump.shutdown()
