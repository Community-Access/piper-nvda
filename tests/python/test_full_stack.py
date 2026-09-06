"""End-to-end test of the Piper Python plumbing against the real helper:
speaking a phrase and playing a demo mp3. Skipped if build/assets missing."""

import os
import threading

import pytest

from synthDrivers.piper import _helperProc, _audio, _protocol as proto

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HELPER = os.path.join(ROOT, "helper", "target", "release", "piper-helper.exe")
ASSETS = os.path.join(ROOT, "assets")
MODEL = os.path.join(ASSETS, "lessac-medium.onnx")
SAMPLE = os.path.join(ASSETS, "sample_lessac.mp3")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(HELPER) and os.path.exists(MODEL)),
    reason="helper build or assets missing",
)


class FakePlayer:
    def __init__(self):
        self.fed_bytes = 0
        self.idled = 0

    def feed(self, data, onDone=None):
        self.fed_bytes += len(data)
        if onDone is not None:
            onDone()

    def idle(self):
        self.idled += 1

    def stop(self):
        pass

    def pause(self, s):
        pass

    def close(self):
        pass


def _espeak_args():
    return ["--espeak-dll", os.path.join(ASSETS, "espeak-ng", "eSpeak NG",
                                         "libespeak-ng.dll"),
            "--espeak-data", os.path.join(ASSETS, "espeak-ng", "eSpeak NG")]


def test_speak_via_stack():
    player = FakePlayer()
    indexes = []
    done = threading.Event()
    pump = _audio.AudioPump(player, indexes.append, done.set)
    hello = threading.Event()

    def on_frame(mt, payload):
        if mt == proto.HELLO:
            hello.set()
        elif mt in (proto.AUDIO, proto.MARKER, proto.DONE):
            pump.handle_frame(mt, payload)

    helper = _helperProc.HelperProcess(HELPER, _espeak_args(), on_frame=on_frame)
    helper.start()
    assert hello.wait(30)
    job = {
        "utteranceId": 1,
        "segments": [{"text": "Testing Piper.", "modelPath": MODEL, "sid": 0,
                      "indexesBefore": [11]}],
        "indexesAfter": [22],
    }
    helper.send(proto.SPEAK, job)
    assert done.wait(60)
    assert player.fed_bytes > 4000
    assert set(indexes) >= {11, 22}
    helper.terminate()
    pump.shutdown()


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="no demo sample")
def test_play_demo_sample():
    player = FakePlayer()
    done = threading.Event()
    pump = _audio.AudioPump(player, lambda i: None, done.set)
    hello = threading.Event()

    def on_frame(mt, payload):
        if mt == proto.HELLO:
            hello.set()
        elif mt in (proto.AUDIO, proto.MARKER, proto.DONE):
            pump.handle_frame(mt, payload)

    helper = _helperProc.HelperProcess(HELPER, _espeak_args(), on_frame=on_frame)
    helper.start()
    assert hello.wait(30)
    helper.send(proto.PLAY_SAMPLE, {"path": SAMPLE})
    assert done.wait(30)
    assert player.fed_bytes > 10000  # decoded mp3 produced audio
    helper.terminate()
    pump.shutdown()
