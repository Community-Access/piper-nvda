"""Per-voice settings, and the list of favourite voices.

NVDA keeps synthesizer settings per synthesizer, not per voice, so moving
between a fast low-quality voice and a slow high-quality one means retuning
rate and pitch every time, and a multi-speaker voice forgets which speaker was
chosen. This remembers those choices against the voice they were made for.

A voice only gets an entry once its settings have been changed while it was
selected. Until then it inherits whatever is currently set, so switching to a
new voice never changes how speech sounds by itself.

Both this and the favourites list live in one file, since both are small and
both are about individual voices. No NVDA or wx dependency, so this is unit
tested directly.
"""

import json
import os

from . import _paths

#: The settings remembered for each voice.
FIELDS = ("rate", "rateBoost", "pitch", "volume", "variant", "variance",
          "noiseScale", "noiseW", "lengthScale")


def path():
    return os.path.join(_paths.data_dir(), "voice_settings.json")


def _read():
    try:
        with open(path(), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load():
    """Return ({voice_key: {field: value}}, [favourite voice keys])."""
    raw = _read()
    voices = raw.get("voices")
    if not isinstance(voices, dict):
        voices = {}
    clean = {}
    for key, settings in voices.items():
        if not isinstance(key, str) or not isinstance(settings, dict):
            continue
        kept = {name: settings[name] for name in FIELDS if name in settings}
        if kept:
            clean[key] = kept
    favorites = raw.get("favorites")
    if not isinstance(favorites, list):
        favorites = []
    return clean, [key for key in favorites if isinstance(key, str) and key]


def save(voices, favorites):
    """Write both halves. Returns what was written."""
    voices = {
        key: {name: value for name, value in settings.items() if name in FIELDS}
        for key, settings in voices.items()
    }
    voices = {key: settings for key, settings in voices.items() if settings}
    favorites = [key for key in favorites if key]
    dest = path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"voices": voices, "favorites": favorites}, f,
                  ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, dest)
    return voices, favorites


def next_favorite(favorites, installed_keys, current):
    """The voice a "next voice" gesture should move to.

    Cycles the favourites that are still installed, and falls back to cycling
    everything installed when no favourite has been chosen, so the gesture is
    useful before anyone has set one up. Returns None when there is nowhere to
    go.
    """
    ring = [key for key in favorites if key in installed_keys]
    if len(ring) < 2:
        ring = sorted(installed_keys)
    if len(ring) < 2:
        return None
    try:
        index = ring.index(current)
    except ValueError:
        return ring[0]
    return ring[(index + 1) % len(ring)]
