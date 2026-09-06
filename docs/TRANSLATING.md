# Translating this add-on

Everything the add-on says is translatable: the interface strings, the add-on
summary and description shown in the Add-on Store, and the user documentation.

## What you need

Nothing but a text editor, or a PO editor such as
[Poedit](https://poedit.net/). The project does not require GNU gettext to be
installed: `tools/i18n.py` extracts strings and compiles translations by
itself, because `xgettext` and `msgfmt` are not normally present on Windows.

## Interface strings

1. Copy `addon/locale/nvda.pot` to
   `addon/locale/<lang>/LC_MESSAGES/nvda.po`, where `<lang>` is the NVDA
   language code (`fr`, `pt_BR`, `de`, ...).
2. Fill in each `msgstr`. Read the `#.` comment above an entry first: those
   are the translator notes written for exactly that purpose, and they say
   what the string is and where it appears.
3. Keep `&` accelerators (they underline the next letter in a button or
   label) and keep every `{name}` placeholder exactly as it is; the add-on
   substitutes values into them by name.
4. Leave an entry's `msgstr` empty rather than guessing. Empty entries fall
   back to English; a wrong translation does not.

Entries marked `#, fuzzy` are machine-generated guesses that need review, and
are deliberately not compiled into the add-on until the marker is removed.

## Documentation

Copy `addon/doc/en/readme.md` to `addon/doc/<lang>/readme.md` and translate
it. NVDA shows the user documentation in their language when it exists.

## Add-on summary and description

These live in `addon/manifest.ini` and appear in the `.pot` like any other
string, with a `#. Translators: add-on summary` comment.

## Checking your work

```
python tools/i18n.py compile
python -m pytest tests/python/test_i18n.py -q
```

`compile` writes a `nvda.mo` next to your `.po` and reports any file it could
not read. Packaging (`python tools/build.py`) compiles translations into the
add-on automatically, so a `.po` in the tree is all that a release needs.

## When strings change

Maintainers run `python tools/i18n.py extract` after changing any
user-visible string, which rewrites `addon/locale/nvda.pot`. A test fails if
the template is out of date, so it should never drift. Merge the new template
into your `.po` with your PO editor's "update from POT" command.

## Credit

Add yourself to the `#` comment header of your `.po` file. Translations are
part of the add-on and are covered by the same licence.
