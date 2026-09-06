"""Filesystem locations for the Piper addon.

The helper binary and espeak-ng data ship inside the addon. Downloaded voices
(one .onnx + .onnx.json per voice) and the voices.json catalog live under the
NVDA user config directory so they survive addon updates.
"""

import os

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

BIN_DIR = os.path.join(_THIS_DIR, "bin")
HELPER_EXE = os.path.join(BIN_DIR, "piper-helper.exe")
ESPEAK_DLL = os.path.join(BIN_DIR, "espeak-ng", "libespeak-ng.dll")
ESPEAK_DATA = os.path.join(BIN_DIR, "espeak-ng")


def data_dir():
    try:
        import globalVars
        base = globalVars.appArgs.configPath
    except Exception:
        base = os.environ.get("PIPER_DATA_DIR", os.path.join(_THIS_DIR, "_data"))
    return os.path.join(base, "piper")


def voices_dir():
    return os.path.join(data_dir(), "voices")


def cache_dir():
    return os.path.join(data_dir(), "cache")


def cache_file():
    """The helper's prepared-audio file. Named here so the voice manager can
    report its size and remove it when no helper is running."""
    return os.path.join(cache_dir(), "piper-audio.kcache")


def catalog_path():
    return os.path.join(data_dir(), "voices.json")


def voice_model_path(voice_key):
    """Local .onnx path for an installed voice."""
    return os.path.join(voices_dir(), voice_key + ".onnx")


def voice_config_path(voice_key):
    return os.path.join(voices_dir(), voice_key + ".onnx.json")


def voice_installed(voice_key):
    return (os.path.isfile(voice_model_path(voice_key))
            and os.path.isfile(voice_config_path(voice_key)))


def installed_voice_keys():
    d = voices_dir()
    if not os.path.isdir(d):
        return []
    keys = []
    for name in os.listdir(d):
        if name.endswith(".onnx") and os.path.isfile(
                os.path.join(d, name + ".json")):
            keys.append(name[:-len(".onnx")])
    return sorted(keys)
