"""Translation tooling for the add-on, with no external dependencies.

GNU gettext's `xgettext` and `msgfmt` are not present on a typical Windows
build machine, so this module implements the two steps the add-on needs:

  python tools/i18n.py extract    rebuild addon/locale/nvda.pot from the
                                  `_("...")` calls in the add-on tree
  python tools/i18n.py compile    compile every addon/locale/<lang>/
                                  LC_MESSAGES/nvda.po to a matching .mo

`extract` follows the NVDA convention of preserving the `# Translators:`
comment directly above each string, which is what translators read for
context. The .mo writer implements the GNU MO format (little-endian, no hash
table), which `gettext.GNUTranslations` reads.

References:
  MO file format: https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html
  PO file format: https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html
"""

import ast
import io
import os
import re
import struct
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "addon")
LOCALE = os.path.join(ADDON, "locale")
POT = os.path.join(LOCALE, "nvda.pot")

MO_MAGIC = 0x950412DE
TRANSLATOR_PREFIX = "# Translators:"

POT_HEADER = '''# Translation template for the Piper Neural Voices NVDA add-on.
# Copyright (C) the Piper Neural Voices contributors.
# This file is distributed under the same license as the add-on.
#
msgid ""
msgstr ""
"Project-Id-Version: piperNeural\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"X-Generator: tools/i18n.py\\n"

'''


class Message:
    """One translatable string plus every place it was found."""

    def __init__(self, msgid):
        self.msgid = msgid
        self.locations = []
        self.comments = []

    def add(self, location, comment):
        self.locations.append(location)
        if comment and comment not in self.comments:
            self.comments.append(comment)


def _translator_comments(source):
    """Map a line number to the `# Translators:` block that ends just above
    it, joined into one line."""
    comments = {}
    block = []
    block_end = None
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return comments
    for kind, text, start, _end, _line in tokens:
        if kind == tokenize.COMMENT:
            stripped = text.strip()
            if stripped.startswith(TRANSLATOR_PREFIX) or block:
                block.append(stripped.lstrip("#").strip())
                block_end = start[0]
            continue
        if kind in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                    tokenize.DEDENT):
            continue
        if block and block_end is not None:
            comments[block_end + 1] = " ".join(block)
        block = []
        block_end = None
    return comments


def extract_file(path):
    """Yield (msgid, line, translator_comment) for one Python file."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return
    comments = _translator_comments(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "_"):
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
            continue
        value = node.args[0].value
        if not isinstance(value, str) or not value:
            continue
        # A call can start a line below its comment when it is wrapped, so
        # look a couple of lines up for the comment block.
        comment = ""
        for line in range(node.lineno, node.lineno - 3, -1):
            if line in comments:
                comment = comments[line]
                break
        yield value, node.lineno, comment


def _manifest_messages(messages):
    """NVDA translates the add-on summary and description from the manifest."""
    manifest = os.path.join(ADDON, "manifest.ini")
    if not os.path.isfile(manifest):
        return
    for line in open(manifest, encoding="utf-8"):
        key, sep, value = line.partition("=")
        if not sep or key.strip() not in ("summary", "description"):
            continue
        text = value.strip().strip('"')
        if not text:
            continue
        message = messages.setdefault(text, Message(text))
        message.add("manifest.ini", "Translators: add-on %s" % key.strip())


def collect():
    """All translatable messages in the add-on, keyed by msgid."""
    messages = {}
    for base, dirs, files in os.walk(ADDON):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "locale", "_data")]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ADDON).replace(os.sep, "/")
            for msgid, line, comment in extract_file(path):
                message = messages.setdefault(msgid, Message(msgid))
                message.add("%s:%d" % (rel, line), comment)
    _manifest_messages(messages)
    return messages


def _po_quote(text):
    escaped = (text.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t"))
    return '"%s"' % escaped


def write_pot(messages, path=POT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(POT_HEADER)
        for msgid in sorted(messages):
            message = messages[msgid]
            for comment in message.comments:
                f.write("#. %s\n" % comment)
            for location in message.locations:
                f.write("#: %s\n" % location)
            f.write("msgid %s\n" % _po_quote(msgid))
            f.write('msgstr ""\n\n')
    return path


def parse_po(path):
    """Return {msgid: msgstr} for a .po file, skipping untranslated and fuzzy
    entries (a fuzzy translation is a guess, not a translation).

    Entries are separated by blank lines, which is what lets the flags above
    an entry (`#, fuzzy`) be attributed to the entry they belong to.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    entries = {}
    for block in re.split(r"\n\s*\n", text):
        msgid, msgstr, fuzzy = _parse_po_block(block)
        if msgid and msgstr and not fuzzy:
            entries[msgid] = msgstr
    entries.pop("", None)
    return entries


def _parse_po_block(block):
    """Parse one PO entry into (msgid, msgstr, fuzzy)."""
    parts = {"msgid": [], "msgstr": []}
    target = None
    fuzzy = False
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            continue
        for keyword in ("msgid", "msgstr"):
            if line.startswith(keyword + " "):
                target = keyword
                parts[target].append(_po_unquote(line[len(keyword) + 1:]))
                break
        else:
            if line.startswith('"') and target:
                parts[target].append(_po_unquote(line))
    return "".join(parts["msgid"]), "".join(parts["msgstr"]), fuzzy


def _po_unquote(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return (text.replace("\\n", "\n").replace("\\t", "\t")
            .replace('\\"', '"').replace("\\\\", "\\"))


def write_mo(entries, path):
    """Write a GNU MO file. Keys and values are str; both are stored UTF-8."""
    items = sorted((k.encode("utf-8"), v.encode("utf-8"))
                   for k, v in entries.items())
    count = len(items)
    key_start = 28 + count * 16
    offsets = []
    payload = bytearray()
    for key, _value in items:
        offsets.append((len(key), key_start + len(payload)))
        payload += key + b"\x00"
    value_start = key_start + len(payload)
    value_offsets = []
    value_payload = bytearray()
    for _key, value in items:
        value_offsets.append((len(value), value_start + len(value_payload)))
        value_payload += value + b"\x00"

    out = bytearray()
    out += struct.pack("<Iiiiiii", MO_MAGIC, 0, count, 28, 28 + count * 8,
                       0, 0)
    for length, offset in offsets:
        out += struct.pack("<ii", length, offset)
    for length, offset in value_offsets:
        out += struct.pack("<ii", length, offset)
    out += payload
    out += value_payload
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(bytes(out))
    return path


def compile_locales(locale_dir=LOCALE, dest_dir=None):
    """Compile every nvda.po under `locale_dir`. Returns the .mo paths.

    `dest_dir` sends the .mo files to a parallel tree (the packaging step
    builds them straight into the staged add-on, so the source tree keeps only
    the .po files under version control).
    """
    written = []
    if not os.path.isdir(locale_dir):
        return written
    for lang in sorted(os.listdir(locale_dir)):
        po = os.path.join(locale_dir, lang, "LC_MESSAGES", "nvda.po")
        if not os.path.isfile(po):
            continue
        out_dir = os.path.join(dest_dir or locale_dir, lang, "LC_MESSAGES")
        write_mo(parse_po(po), os.path.join(out_dir, "nvda.mo"))
        written.append(os.path.join(out_dir, "nvda.mo"))
    return written


def main(argv):
    command = argv[1] if len(argv) > 1 else "extract"
    if command == "extract":
        messages = collect()
        path = write_pot(messages)
        print("wrote %s (%d messages)" % (path, len(messages)))
    elif command == "compile":
        written = compile_locales()
        if not written:
            print("no .po files under %s" % LOCALE)
        for path in written:
            print("wrote %s" % path)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
