"""Measure the pure IPC round-trip overhead (PING -> PONG) that an in-process
design would eliminate. This is the cost of the subprocess boundary with no
inference involved."""

import importlib.util
import json
import os
import struct
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
H = os.path.join(ROOT, "helper", "target", "release", "piper-helper.exe")

spec = importlib.util.spec_from_file_location(
    "pp", os.path.join(ROOT, "addon", "synthDrivers", "piper", "_protocol.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

proc = subprocess.Popen(
    [H, "--espeak-dll", os.path.join(A, "espeak-ng", "eSpeak NG", "libespeak-ng.dll"),
     "--espeak-data", os.path.join(A, "espeak-ng", "eSpeak NG")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
ev = []
lk = threading.Condition()


def readn(k):
    b = b""
    while len(b) < k:
        c = proc.stdout.read(k - len(b))
        if not c:
            return None
        b += c
    return b


def rd():
    while True:
        h = readn(4)
        if h is None:
            break
        (n,) = struct.unpack("<I", h)
        body = readn(n)
        with lk:
            ev.append(body[0])
            lk.notify_all()


threading.Thread(target=rd, daemon=True).start()


def wait_count(target, to=10):
    end = time.perf_counter() + to
    with lk:
        while len([e for e in ev if e == 0x85]) < target:
            if time.perf_counter() > end:
                return
            lk.wait(0.1)


def send(ty, o):
    pl = json.dumps(o).encode()
    proc.stdin.write(struct.pack("<I", len(pl) + 1) + bytes([ty]) + pl)
    proc.stdin.flush()


# wait for HELLO
time.sleep(1.0)
N = 200
rtts = []
for _ in range(N):
    before = len([e for e in ev if e == 0x85])
    t0 = time.perf_counter()
    send(0x05, {})  # PING
    wait_count(before + 1, 5)
    rtts.append((time.perf_counter() - t0) * 1000)
rtts.sort()
print("IPC round-trip (PING->PONG) over %d calls:" % N)
print("  p50 %.3f ms   p95 %.3f ms   max %.3f ms"
      % (rtts[len(rtts) // 2], rtts[int(len(rtts) * 0.95)], rtts[-1]))
send(0x06, {})
