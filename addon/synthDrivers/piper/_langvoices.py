"""Per-language voice assignments for automatic language switching.

NVDA emits a language change command when a document declares a different
language. By default the driver picks the first installed voice whose language
matches. This module stores an explicit choice per language so a user with
several voices for one language gets the one they actually want, and so a
language can be pinned to a voice whose own language tag is broader (say a
generic Spanish voice for `es-AR`).

Stored as JSON in the addon data directory. No NVDA or wx dependency.
"""

import json
import os

from . import _paths


def path():
    return os.path.join(_paths.data_dir(), "language_voices.json")


def normalize(language):
    """Language tags reach us as `en_US`, `en-US`, or `en`; key on the
    lowercase underscore form so lookups are stable."""
    return (language or "").replace("-", "_").lower()


def load():
    """Return {language: voice_key}. Missing or damaged files read as empty."""
    try:
        with open(path(), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        normalize(lang): key
        for lang, key in raw.items()
        if isinstance(lang, str) and isinstance(key, str) and lang and key
    }


def save(mapping):
    """Write the mapping, dropping blank entries. Returns what was written."""
    clean = {normalize(lang): key
             for lang, key in mapping.items() if lang and key}
    dest = path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, dest)
    return clean


def resolve(mapping, language, installed_keys):
    """Voice key assigned to `language`, or None.

    Falls back from the full tag to the primary subtag, so an assignment for
    `pt` also covers `pt-BR` unless `pt_br` has its own entry. Assignments
    naming a voice that is no longer installed are ignored.
    """
    lang = normalize(language)
    if not lang:
        return None
    candidates = [lang]
    base = lang.split("_", 1)[0]
    if base != lang:
        candidates.append(base)
    for candidate in candidates:
        key = mapping.get(candidate)
        if key and key in installed_keys:
            return key
    return None
