"""Measure Piper streaming first-audio latency (SPEAK -> first AUDIO frame)."""

import importlib.util
import json
import os
import struct
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
H = os.path.join(ROOT, "helper", "target", "release", "piper-helper.exe")
MODEL = os.path.join(A, sys.argv[1] if len(sys.argv) > 1 else "lessac-medium.onnx")

spec = importlib.util.spec_from_file_location(
    "pp", os.path.join(ROOT, "addon", "synthDrivers", "piper", "_protocol.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

proc = subprocess.Popen(
    [H, "--espeak-dll", os.path.join(A, "espeak-ng", "eSpeak NG", "libespeak-ng.dll"),
     "--espeak-data", os.path.join(A, "espeak-ng", "eSpeak NG"),
     "--cache-dir", os.path.join(A, "_benchcache")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
ev = []
lk = threading.Condition()


def readn(k):
    buf = b""
    while len(buf) < k:
        c = proc.stdout.read(k - len(buf))
        if not c:
            return None
        buf += c
    return buf


def rd():
    while True:
        h = readn(4)
        if h is None:
            break
        (n,) = struct.unpack("<I", h)
        b = readn(n)
        if b is None:
            break
        with lk:
            ev.append((time.perf_counter(), b[0]))
            lk.notify_all()


threading.Thread(target=rd, daemon=True).start()


def wait(ty, since, to=30):
    end = time.perf_counter() + to
    with lk:
        i = since
        while True:
            while i < len(ev):
                if ev[i][1] == ty:
                    return ev[i][0], i
                i += 1
            if time.perf_counter() > end:
                return None, i
            lk.wait(0.2)


def send(ty, o):
    pl = json.dumps(o).encode()
    proc.stdin.write(struct.pack("<I", len(pl) + 1) + bytes([ty]) + pl)
    proc.stdin.flush()


def speak(uid, text, cm):
    return {"utteranceId": uid,
            "segments": [{"text": text, "modelPath": MODEL, "charMode": cm}],
            "indexesAfter": []}


wait(0x01, 0, 30)
send(0x02, speak(1, "warm up", False))
wait(0x83, 0, 30)
print("Piper first-audio, model:", os.path.basename(MODEL))
uid = 1
for label, text, cm in [
    ("char echo", "h", True),
    ("word", "responsive", False),
    ("line", "Documents folder, 42 items.", False),
    ("sentence", "The quick brown fox jumps over the lazy dog near the river bank.", False),
]:
    s = []
    for _ in range(5):
        uid += 1
        idx = len(ev)
        t0 = time.perf_counter()
        send(0x02, speak(uid, text, cm))
        ta, _i = wait(0x81, idx, 30)
        wait(0x83, idx, 30)
        s.append((ta - t0) * 1000)
    s.sort()
    half = len(s) // 2
    print("  %-10s p50 %5.0f ms (min %.0f)" % (label, s[half], s[0]))
send(0x06, {})
