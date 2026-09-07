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
        # Serializes death handling: the watchdog (on a hang) and the reader
        # thread (on EOF after the watchdog's kill) both report the same
        # death, and without the lock both would restart.
        self._death_lock = threading.Lock()
        self._alive = False
        self._gave_up = False
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
            target=self._read_loop, args=(self._proc,),
            name="piperReader", daemon=True
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

    @staticmethod
    def _read_exactly(proc, n):
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

    def _read_loop(self, proc):
        """Serve one process for its whole life. Bound to the process it was
        started for, never `self._proc`, so a reader that outlives a restart
        cannot read from - or report the death of - the replacement."""
        read = lambda n: self._read_exactly(proc, n)  # noqa: E731
        while True:
            try:
                frame = proto.read_frame(read)
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
            self._handle_death(proc)

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
        while not self._stopping and not self._gave_up:
            time.sleep(_PING_INTERVAL)
            if self._stopping or self._gave_up:
                break
            if not self._alive:
                continue
            try:
                self.send(proto.PING, {})
            except Exception:
                continue
            if time.monotonic() - self._last_pong > _PING_INTERVAL + _PING_TIMEOUT:
                log.warning("piper: helper unresponsive, restarting")
                self._handle_death(self._proc)

    def _handle_death(self, dead_proc):
        """Handle the death (or hang) of `dead_proc`, restarting within the
        budget. Both the watchdog and the dead process's reader thread call
        this for the same event; the lock and the identity check make the
        second caller a no-op instead of a second restart."""
        with self._death_lock:
            if self._stopping or dead_proc is None or dead_proc is not self._proc:
                return
            # Kill first: on a hang the process is still running, and it must
            # not survive - especially not on the giving-up path, where a
            # live orphan with a full stdin pipe would block send() forever.
            try:
                dead_proc.kill()
            except Exception:
                pass
            self._alive = False
            now = time.monotonic()
            self._restart_times = [
                t for t in self._restart_times if now - t < 60.0]
            if len(self._restart_times) >= _MAX_RESTARTS_PER_MINUTE:
                log.error("piper: helper crashed too often; giving up")
                # send() must fail fast from here on, not write into a corpse.
                self._proc = None
                self._gave_up = True
                return
            self._restart_times.append(now)
            backoff = 0.5 * (2 ** (len(self._restart_times) - 1))
            time.sleep(backoff)
            if self._stopping:
                return
            try:
                self._spawn()
                log.info("piper: helper restarted")
            except Exception:
                log.exception("piper: helper restart failed")
                return
        # Outside the lock: the driver's re-send callbacks go through send(),
        # and holding the death lock across them invites deadlock.
        if self._on_restart is not None:
            self._on_restart()
