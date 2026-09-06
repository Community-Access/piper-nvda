"""User pronunciation lexicon: whole-word IPA overrides.

Stored as JSON in the addon data directory so it survives addon updates and
can be edited, backed up, or shared as a plain file. The helper receives the
whole map over the protocol; `rev` increases on every save so the helper only
invalidates cached audio for chunks that actually contain an override.

This module has no NVDA or wx dependency, so it is unit tested directly.
"""

import json
import os

from . import _paths

_DEFAULT = {"rev": 0, "entries": {}}


def path():
    return os.path.join(_paths.data_dir(), "lexicon.json")


def load():
    """Return (rev, {word: ipa}). Missing or damaged files read as empty."""
    try:
        with open(path(), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return _DEFAULT["rev"], dict(_DEFAULT["entries"])
    if not isinstance(raw, dict):
        return 0, {}
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    clean = {}
    for word, ipa in entries.items():
        if isinstance(word, str) and isinstance(ipa, str):
            word = word.strip().lower()
            ipa = ipa.strip()
            if word and ipa:
                clean[word] = ipa
    try:
        rev = int(raw.get("rev", 0))
    except (TypeError, ValueError):
        rev = 0
    return rev, clean


def save(entries):
    """Write `entries`, bumping the revision. Returns the new (rev, entries)."""
    rev, _old = load()
    clean = {}
    for word, ipa in entries.items():
        word = (word or "").strip().lower()
        ipa = (ipa or "").strip()
        if word and ipa:
            clean[word] = ipa
    rev += 1
    dest = path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"rev": rev, "entries": clean}, f,
                  ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, dest)
    return rev, clean


def message(rev, entries):
    """Build the SET_LEXICON payload for the helper."""
    return {"rev": rev, "entries": entries}
