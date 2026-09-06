"""Stub of NVDA's symbol pronunciation lookup."""

#: What the stub knows, keyed by locale then symbol.
SYMBOLS = {
    "en": {".": "dot", ",": "comma", " ": "space", "?": "question"},
    "fr": {".": "point", ",": "virgule"},
}


def processSpeechSymbol(locale, symbol):
    """Return the symbol's spoken name, or the symbol when there is none."""
    table = SYMBOLS.get(locale.split("_")[0].lower(), {})
    return table.get(symbol, symbol)
