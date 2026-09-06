"""Extra words and phrases to prepare in the background.

The helper always warms the alphabet and a list of words NVDA says constantly
(roles, states, punctuation names), so those speak with no delay at all. What
it cannot know is the vocabulary of a particular person's day: the name of the
app they live in, a colleague's name, a status message their tools repeat.
This is the list they add themselves.

Entries are capped in length, because preparation only pays off when the
phrase reaches the synthesizer as a single chunk. The helper splits an
utterance into clauses and splits the first clause near 40 characters to get
speech started sooner, so a phrase longer than that would be prepared as text
that is never asked for as a unit.

No NVDA or wx dependency, so this is unit tested directly.
"""

import json
import os

from . import _paths

#: Longest phrase worth preparing, in characters. Matches the helper's
#: first-chunk target: beyond it, an utterance is split and the prepared audio
#: would never be looked up.
MAX_LENGTH = 40

#: Most entries to keep. The cache holds a few thousand entries in total and
#: is shared with the built-in list and with whatever has been spoken, so a
#: runaway list would evict the things it was meant to speed up.
MAX_ENTRIES = 500


def path():
    return os.path.join(_paths.data_dir(), "warmup.json")


def clean(words):
    """Normalize a list of phrases: trimmed, de-duplicated, within limits.

    Order is preserved, since it is the order the user put them in and the
    order they are prepared.
    """
    seen = set()
    out = []
    for word in words or ():
        if not isinstance(word, str):
            continue
        word = " ".join(word.split())
        if not word or len(word) > MAX_LENGTH:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
        if len(out) >= MAX_ENTRIES:
            break
    return out


def load():
    """Return the user's list. Missing or damaged files read as empty."""
    try:
        with open(path(), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("words")
    if not isinstance(raw, list):
        return []
    return clean(raw)


def save(words):
    """Write the list, normalized. Returns what was written."""
    words = clean(words)
    dest = path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"words": words}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, dest)
    return words
