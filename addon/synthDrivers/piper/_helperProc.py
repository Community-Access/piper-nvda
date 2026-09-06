"""Manages the piper-helper child process: startup handshake, a reader
thread that dispatches inbound frames to callbacks, a ping watchdog, and
automatic restart with backoff after a crash or hang.

This module is deliberately free of NVDA imports so its logic can be tested
with a stub helper executable.
"""

import os
import subprocess
import threading
import time

from . import _protocol as proto

try:
    from logHandler import log
except Exception:  # pragma: no cover - outside NVDA
    import logging
    log = logging.getLogger("piper")

# Windows process creation flags (avoid importing the whole subprocess table).
_CREATE_NO_WINDOW = 0x08000000

_PING_INTERVAL = 10.0
_PING_TIMEOUT = 8.0
_MAX_RESTARTS_PER_MINUTE = 3


class HelperProcess:
    def __init__(self, exe, args, on_frame, on_restart=None):
        """`args` is the list of CLI arguments after the exe. `on_frame` is
        called from the reader thread as on_frame(msg_type, payload). It must
        be quick and thread safe. `on_restart` (optional) is called after a
        successful restart so the driver can re-send parameters."""
        self._exe = exe
        self._args = list(args)
        self._on_frame = on_frame
        self._on_restart = on_restart
        self._proc = None
        self._reader = None
        self._write_lock = threading.Lock()
        self._alive = False
        self._last_pong = 0.0
        self._restart_times = []
        self._watchdog = None
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        self._stopping = False
        self._spawn()
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, name="piperWatchdog", daemon=True
        )
        self._watchdog.start()

    def _spawn(self):
        creationflags = _CREATE_NO_WINDOW if os.name == "nt" else 0
        self._proc = subprocess.Popen(
            [self._exe] + self._args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            bufsize=0,
        )
        self._alive = True
        self._last_pong = time.monotonic()
        self._reader = threading.Thread(
            target=self._read_loop, name="piperReader", daemon=True
        )
        self._reader.start()

    def terminate(self):
        self._stopping = True
        self._alive = False
        try:
            self.send(proto.SHUTDOWN, {})
        except Exception:
            pass
        proc = self._proc
        if proc is not None:
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._proc = None

    # -- io ----------------------------------------------------------------

    def _read_exactly(self, n):
        proc = self._proc
        if proc is None:
            return None
        buf = b""
        while len(buf) < n:
            try:
                chunk = proc.stdout.read(n - len(buf))
            except Exception:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf

    def _read_loop(self):
        while self._alive:
            try:
                frame = proto.read_frame(self._read_exactly)
            except Exception:
                frame = None
            if frame is None:
                break
            msg_type, payload = frame
            if msg_type == proto.PONG:
                self._last_pong = time.monotonic()
                continue
            try:
                self._on_frame(msg_type, payload)
            except Exception:
                log.exception("piper: on_frame callback failed")
        # Reader exited: the process died or is shutting down.
        if not self._stopping:
            self._handle_death()

    def send(self, msg_type, obj):
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise IOError("helper not running")
        data = proto.encode_json(msg_type, obj)
        with self._write_lock:
            proc.stdin.write(data)
            proc.stdin.flush()

    def send_raw(self, frame_bytes):
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise IOError("helper not running")
        with self._write_lock:
            proc.stdin.write(frame_bytes)
            proc.stdin.flush()

    # -- resilience --------------------------------------------------------

    def _watchdog_loop(self):
        while self._alive and not self._stopping:
            time.sleep(_PING_INTERVAL)
            if not self._alive or self._stopping:
                break
            try:
                self.send(proto.PING, {})
            except Exception:
                continue
            if time.monotonic() - self._last_pong > _PING_INTERVAL + _PING_TIMEOUT:
                log.warning("piper: helper unresponsive, restarting")
                self._handle_death()

    def _handle_death(self):
        if self._stopping:
            return
        self._alive = False
        now = time.monotonic()
        self._restart_times = [t for t in self._restart_times if now - t < 60.0]
        if len(self._restart_times) >= _MAX_RESTARTS_PER_MINUTE:
            log.error("piper: helper crashed too often; giving up")
            return
        self._restart_times.append(now)
        backoff = 0.5 * (2 ** (len(self._restart_times) - 1))
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        time.sleep(backoff)
        if self._stopping:
            return
        try:
            self._spawn()
            log.info("piper: helper restarted")
            if self._on_restart is not None:
                self._on_restart()
        except Exception:
            log.exception("piper: helper restart failed")
