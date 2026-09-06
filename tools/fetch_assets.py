"""Fetch development assets for the Piper NVDA helper: the espeak-ng runtime
and a couple of test voices (model + config + demo sample). Voices ship to
users via runtime download; these are only for building and testing.

Usage: python tools/fetch_assets.py
"""

import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

VOICES = [
    ("en/en_US/lessac/medium/en_US-lessac-medium", "lessac-medium"),
    ("en/en_US/ryan/low/en_US-ryan-low", "ryan-low"),
]


def fetch(url, dest):
    if os.path.exists(dest):
        print("exists:", os.path.basename(dest))
        return
    print("downloading:", url)
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for rel, local in VOICES:
        fetch(HF + rel + ".onnx", os.path.join(ASSETS, local + ".onnx"))
        fetch(HF + rel + ".onnx.json", os.path.join(ASSETS, local + ".onnx.json"))
    fetch(HF + "en/en_US/lessac/medium/samples/speaker_0.mp3",
          os.path.join(ASSETS, "sample_lessac.mp3"))

    espeak = os.path.join(ASSETS, "espeak-ng", "eSpeak NG", "libespeak-ng.dll")
    if not os.path.exists(espeak):
        print("Downloading espeak-ng 1.52.0 MSI and extracting...")
        msi = os.path.join(ASSETS, "espeak-ng.msi")
        fetch("https://github.com/espeak-ng/espeak-ng/releases/download/"
              "1.52.0/espeak-ng.msi", msi)
        target = os.path.join(ASSETS, "espeak-ng")
        os.makedirs(target, exist_ok=True)
        subprocess.check_call(["msiexec", "/a", os.path.abspath(msi), "/qn",
                               "TARGETDIR=" + os.path.abspath(target)])
    print("done")


if __name__ == "__main__":
    sys.exit(main())
