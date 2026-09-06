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


#: The characters worth preparing the spoken name of. Reading by character
#: and spelling a word are where a delay is felt most, and punctuation is as
#: common there as letters.
SYMBOL_CHARACTERS = (
    " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "–—‘’“”…•°©®™€£¥¢§¶"
    "×÷±≠≤≥→←↑↓½¼¾«»"
)


#: Mirrors of the helper's built-in warmup lists (helper/src/server.rs), so
#: the voice manager can show what is prepared automatically without the
#: helper running. A unit test compares each mirror against the Rust source,
#: so they cannot drift.
BUILTIN_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"

BUILTIN_SYMBOLS = (
    "!", "\"", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",", "-", ".",
    "/", ":", ";", "<", "=", ">", "?", "@", "[", "\\", "]", "^", "_", "`",
    "{", "|", "}", "~", "–", "—", "‘", "’", "“",
    "”", "…", "•", "°", "©", "®", "™",
    "€", "£", "¥", "¢", "§", "¶", "×",
    "÷", "±", "≠", "≤", "≥", "→", "←",
    "↑", "↓", "½", "¼", "¾", "«", "»",
)

BUILTIN_SYMBOL_NAMES = (
    "bang", "quote", "dollar", "percent", "and", "tick", "left paren",
    "right paren", "star", "plus", "comma", "dash", "dot", "slash", "colon",
    "semi", "less", "equals", "greater", "question", "at", "left bracket",
    "right bracket", "caret", "line", "graav", "left brace", "bar",
    "right brace", "tilda", "en dash", "em dash", "left tick", "right tick",
    "left quote", "right quote", "dot dot dot", "bullet", "degrees",
    "copyright", "registered", "trademark", "euro", "pound", "yen", "cents",
    "section", "paragraph marker", "times", "divide by", "plus or Minus",
    "not equal to", "less- than or equal to", "greater-than or equal to",
    "right arrow", "left arrow", "up arrow", "down arrow", "one half",
    "one quarter", "three quarters", "double left pointing angle bracket",
    "double right pointing angle bracket",
)

BUILTIN_NUMBERS = (
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
    "million", "billion",
)

BUILTIN_WORDS = (
    "button", "checkbox", "check box", "radio button", "menu", "menu item",
    "menu bar", "list", "list item", "tree view", "tab", "edit", "combo box",
    "slider", "spin button", "progress bar", "link", "heading", "graphic",
    "table", "row", "column", "cell", "dialog", "window", "pane", "document",
    "toolbar", "status bar", "separator", "grouping", "region", "banner",
    "navigation", "article", "section", "form", "text", "password", "search",
    "toggle button", "split button", "scroll bar", "header", "footer",
    "selected", "not selected", "checked", "not checked", "half checked",
    "pressed", "not pressed", "expanded", "collapsed", "unavailable",
    "read only", "required", "invalid entry", "busy", "clickable", "editable",
    "multi line", "has pop up", "current", "modal", "on", "off",
    "blank", "empty", "space", "tab", "enter", "delete", "back space",
    "capital", "cap", "yes", "no", "okay", "cancel", "close", "open", "more",
    "less", "of", "level", "with", "contains", "out of", "new line", "line",
    "warning", "error", "alert",
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten",
    "dot", "comma", "star", "dash", "slash", "colon", "semicolon", "quote",
    "left paren", "right paren", "percent", "dollar", "at", "number",
    "ampersand", "plus", "minus", "equals", "greater", "less than",
)


def builtin_items(language=None):
    """Everything prepared without being asked, in the order it is prepared.

    Mirrors the helper's `warmup_items` (helper/src/server.rs): the user's
    own phrases come first and are listed elsewhere; then the characters,
    the symbols, the symbol names, the numbers, and the common words. When
    NVDA can be asked, the driver sends its symbol names in the user's
    language ahead of the built-ins and the helper skips its English list,
    so the view does the same.
    """
    names = symbol_words(language)
    if names:
        return (names + list(BUILTIN_CHARS) + list(BUILTIN_SYMBOLS)
                + list(BUILTIN_NUMBERS) + list(BUILTIN_WORDS))
    return (list(BUILTIN_CHARS) + list(BUILTIN_SYMBOLS)
            + list(BUILTIN_SYMBOL_NAMES) + list(BUILTIN_NUMBERS)
            + list(BUILTIN_WORDS))


def path():
    return os.path.join(_paths.data_dir(), "warmup.json")


def symbol_words(language=None):
    """The names NVDA gives punctuation, in the user's own language.

    The helper carries an English list, which is no use to someone reading
    French: it would prepare "dot" while NVDA says "point". NVDA knows the
    names for every locale it ships, so ask it rather than shipping tables we
    cannot check. Returns an empty list when NVDA cannot be asked, and the
    helper's own list is used instead.
    """
    try:
        import characterProcessing
        import languageHandler
        locale = language or languageHandler.getLanguage()
    except Exception:
        return []
    names = []
    seen = set()
    for character in SYMBOL_CHARACTERS:
        try:
            name = characterProcessing.processSpeechSymbol(locale, character)
        except Exception:
            return []
        # A character with no name comes back unchanged, and preparing the
        # character itself is the helper's job.
        if not name or name == character or len(name) > MAX_LENGTH:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            names.append(name)
    return names


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
