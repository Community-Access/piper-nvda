"""Audio pump: turns the helper's AUDIO/MARKER/DONE frame stream into
WavePlayer feeds and NVDA index/done notifications.

Design: helper frames are enqueued from the reader thread and consumed by a
dedicated feeder thread. Accumulated PCM is flushed to the player with an
onDone callback exactly at each MARKER position, so an index fires only once
the audio preceding it has actually played. This is what keeps say-all,
braille tethering, and spelling in sync.

The WavePlayer and the two notify callbacks are injected so this module can
be unit tested without NVDA.
"""

import queue
import threading

from . import _protocol as proto

try:
    from logHandler import log
except Exception:  # pragma: no cover
    import logging
    log = logging.getLogger("kokoro")

# Sentinels for the feeder queue.
_DONE = ("done",)
_STOP = ("stop",)


class AudioPump:
    def __init__(self, player, on_index, on_done):
        """`player` is an nvwave.WavePlayer-like object exposing feed(data,
        onDone=None), idle(), stop(), pause(switch), close(). `on_index` is
        called as on_index(index:int) when a marker's audio has played.
        `on_done` is called once an utterance's audio has finished."""
        self._player = player
        self._on_index = on_index
        self._on_done = on_done
        self._q = queue.Queue()
        self._buffer = bytearray()
        self._thread = threading.Thread(
            target=self._feed_loop, name="kokoroFeeder", daemon=True
        )
        self._thread.start()

    # -- frame intake (called from the helper reader thread) --------------

    def handle_frame(self, msg_type, payload):
        if msg_type == proto.AUDIO:
            _, pcm = proto.parse_audio(payload)
            self._q.put(("audio", pcm))
        elif msg_type == proto.MARKER:
            header = proto.parse_json(payload)
            self._q.put(("marker", header["index"]))
        elif msg_type == proto.DONE:
            self._q.put(_DONE)

    def cancel(self):
        """Immediately stop playback and discard everything queued. Called on
        every interrupting keystroke, so it must be fast."""
        self._player.stop()
        _drain(self._q)
        self._buffer = bytearray()
        # Wake the feeder in case it is blocked so it re-checks state.
        self._q.put(("flush", None))

    def pause(self, switch):
        self._player.pause(switch)

    def shutdown(self):
        self._q.put(_STOP)

    # -- feeder thread -----------------------------------------------------

    def _feed_loop(self):
        while True:
            item = self._q.get()
            kind = item[0]
            if kind == "audio":
                self._buffer += item[1]
            elif kind == "marker":
                self._flush(on_done=self._make_index_cb(item[1]))
            elif kind == "done":
                self._flush()
                self._finish_done()
            elif kind == "flush":
                # Buffer was already cleared by cancel(); nothing to do.
                pass
            elif kind == "stop":
                break

    def _flush(self, on_done=None):
        if not self._buffer:
            if on_done is not None:
                on_done()
            return
        data = bytes(self._buffer)
        self._buffer = bytearray()
        try:
            if on_done is not None:
                self._player.feed(data, onDone=on_done)
            else:
                self._player.feed(data)
        except Exception:
            log.exception("kokoro: player.feed failed")
            if on_done is not None:
                on_done()

    def _finish_done(self):
        try:
            self._player.idle()
        except Exception:
            log.exception("kokoro: player.idle failed")
        try:
            self._on_done()
        except Exception:
            log.exception("kokoro: on_done callback failed")

    def _make_index_cb(self, index):
        def cb():
            try:
                self._on_index(index)
            except Exception:
                log.exception("kokoro: on_index callback failed")
        return cb


def _drain(q):
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        pass
