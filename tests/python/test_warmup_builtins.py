"""The read-only view of the helper's built-in warmup must not drift.

The lists themselves live in the helper (helper/src/server.rs) because the
helper does the preparing; `_warmup` mirrors them so the voice manager can
show what is prepared automatically without the helper running. These tests
read the Rust source and compare, so an edit to either side fails here until
the other side matches.
"""

import os
import re

import pytest

from synthDrivers.piper import _warmup

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_RS = os.path.join(ROOT, "helper", "src", "server.rs")

with open(SERVER_RS, encoding="utf-8") as f:
    RUST = f.read()


def _rust_string_list(name):
    m = re.search(r"const %s: &\[&str\] = &\[(.*?)\];" % name, RUST, re.S)
    assert m, "const %s not found in server.rs" % name
    return [re.sub(r"\\(.)", r"\1", s)
            for s in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))]


def _rust_string(name):
    m = re.search(r'const %s: &str = "((?:[^"\\]|\\.)*)";' % name, RUST)
    assert m, "const %s not found in server.rs" % name
    return re.sub(r"\\(.)", r"\1", m.group(1))


@pytest.mark.parametrize("rust_name,mirror", [
    ("WARMUP_SYMBOLS", _warmup.BUILTIN_SYMBOLS),
    ("WARMUP_SYMBOL_NAMES", _warmup.BUILTIN_SYMBOL_NAMES),
    ("WARMUP_NUMBERS", _warmup.BUILTIN_NUMBERS),
    ("WARMUP_WORDS", _warmup.BUILTIN_WORDS),
])
def test_mirror_matches_helper(rust_name, mirror):
    assert list(mirror) == _rust_string_list(rust_name)


def test_chars_match_helper():
    assert _warmup.BUILTIN_CHARS == _rust_string("WARMUP_CHARS")


def test_builtin_items_order_without_nvda(monkeypatch):
    """No NVDA names: the helper's own order, English names included."""
    monkeypatch.setattr(_warmup, "symbol_words", lambda language=None: [])
    items = _warmup.builtin_items()
    expected = (list(_warmup.BUILTIN_CHARS) + list(_warmup.BUILTIN_SYMBOLS)
                + list(_warmup.BUILTIN_SYMBOL_NAMES)
                + list(_warmup.BUILTIN_NUMBERS) + list(_warmup.BUILTIN_WORDS))
    assert items == expected


def test_builtin_items_prefers_nvdas_names(monkeypatch):
    """With NVDA's localized names, they lead and the English list is
    skipped, matching what the driver sends and the helper prepares."""
    monkeypatch.setattr(_warmup, "symbol_words",
                        lambda language=None: ["point", "virgule"])
    items = _warmup.builtin_items()
    assert items[:2] == ["point", "virgule"]
    assert "graav" not in items
    assert items[2:2 + len(_warmup.BUILTIN_CHARS)] == list(_warmup.BUILTIN_CHARS)
