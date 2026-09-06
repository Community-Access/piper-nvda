"""Stub of nvwave with a recording fake WavePlayer for tests."""

import enum


class AudioPurpose(enum.Enum):
    SPEECH = 1
    SOUNDS = 2


class WavePlayer:
    def __init__(self, channels=1, samplesPerSec=24000, bitsPerSample=16,
                 outputDevice=None, wantDucking=True, purpose=None):
        self.fed = []
        self.stopped = 0
        self.idled = 0
        self.paused = None
        self.closed = False

    def feed(self, data, onDone=None):
        self.fed.append(data)
        if onDone is not None:
            onDone()

    def idle(self):
        self.idled += 1

    def stop(self):
        self.stopped += 1

    def pause(self, switch):
        self.paused = switch

    def sync(self):
        pass

    def close(self):
        self.closed = True
