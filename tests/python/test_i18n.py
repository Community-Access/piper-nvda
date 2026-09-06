"""Tests for the translation pipeline in tools/i18n.py.

There is no msgfmt on the build machines, so the .mo writer is ours; these
tests prove a translated string survives extract -> po -> mo -> gettext.
"""

import gettext
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import i18n  # noqa: E402


def test_extracts_strings_with_translator_comments():
    messages = i18n.collect()
    # A string from the voice manager, with the comment translators read.
    assert "&Download" in messages
    assert any("Translators:" in c for c in messages["&Download"].comments)
    # Every extracted message records where it came from.
    assert all(m.locations for m in messages.values())


def test_extracts_manifest_summary():
    messages = i18n.collect()
    assert "Piper Neural Voices" in messages


def test_pot_is_current(tmp_path):
    """The checked-in template must match the source, or translators work
    from a stale list."""
    generated = i18n.write_pot(i18n.collect(), str(tmp_path / "nvda.pot"))
    with open(generated, encoding="utf-8") as f:
        fresh = f.read()
    with open(i18n.POT, encoding="utf-8") as f:
        committed = f.read()
    assert fresh == committed, "run: python tools/i18n.py extract"


def test_po_to_mo_roundtrip(tmp_path):
    po = tmp_path / "xx" / "LC_MESSAGES" / "nvda.po"
    po.parent.mkdir(parents=True)
    po.write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        '#. Translators: a button.\n'
        'msgid "&Download"\n'
        'msgstr "&Descargar"\n\n'
        '#, fuzzy\n'
        'msgid "&Close"\n'
        'msgstr "guess"\n\n'
        'msgid "&Remove"\n'
        'msgstr ""\n',
        encoding="utf-8")

    written = i18n.compile_locales(str(tmp_path))
    assert len(written) == 1

    with open(written[0], "rb") as f:
        translation = gettext.GNUTranslations(f)
    assert translation.gettext("&Download") == "&Descargar"
    # Fuzzy entries are guesses and must not ship.
    assert translation.gettext("&Close") == "&Close"
    # Untranslated entries fall through to the source string.
    assert translation.gettext("&Remove") == "&Remove"


def test_compile_can_target_a_separate_tree(tmp_path):
    src = tmp_path / "src"
    (src / "fr" / "LC_MESSAGES").mkdir(parents=True)
    (src / "fr" / "LC_MESSAGES" / "nvda.po").write_text(
        'msgid "&Save"\nmsgstr "&Enregistrer"\n', encoding="utf-8")
    dest = tmp_path / "build"
    written = i18n.compile_locales(str(src), str(dest))
    assert written == [str(dest / "fr" / "LC_MESSAGES" / "nvda.mo")]
    assert os.path.isfile(written[0])


@pytest.mark.parametrize("text", ["plain", 'has "quotes"', "two\nlines",
                                  "unicode ɛː"])
def test_po_quoting_roundtrip(text, tmp_path):
    po = tmp_path / "xx" / "LC_MESSAGES" / "nvda.po"
    po.parent.mkdir(parents=True)
    po.write_text("msgid %s\nmsgstr %s\n"
                  % (i18n._po_quote(text), i18n._po_quote(text + "!")),
                  encoding="utf-8")
    assert i18n.parse_po(str(po)) == {text: text + "!"}
