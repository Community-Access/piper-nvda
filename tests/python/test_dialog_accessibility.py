"""Mechanical accessibility checks over the add-on's dialogs.

A dialog cannot be driven headlessly, and no test replaces someone listening
to it. What a test can do is catch the faults that are decidable from the
source and that a person auditing by ear would waste their attention on:
a control with no label, two controls in the same dialog claiming the same
accelerator, an accelerator that is not on any letter, a dialog with no title,
and a dialog that never puts focus anywhere.

Everything here reads the source with `ast`, so it stays true whether or not
wx can be imported.
"""

import ast
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_SOURCE = os.path.join(ROOT, "addon", "synthDrivers", "piper", "_manager_ui.py")

#: Controls that carry their own visible label.
SELF_LABELLING = {"Button", "CheckBox", "RadioButton", "StaticText"}
#: Controls that have no label of their own and need a StaticText beside them.
NEEDS_A_LABEL = {"TextCtrl", "ListBox", "CheckListBox", "Choice", "ComboBox",
                 "ListCtrl", "SpinCtrl"}


def _string_of(node):
    """The literal text of `_("x")`, `"x"`, or `"x".format(...)`; else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "_" and node.args:
            return _string_of(node.args[0])
        # `_("...").format(...)`
        if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            return _string_of(node.func.value)
    if isinstance(node, ast.JoinedStr):
        return None
    return None


def _keyword(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


class Dialog:
    """What one dialog class in the source says about itself."""

    def __init__(self, node):
        self.name = node.name
        self.title = None
        self.labels = []          # (control, text)
        self.controls = []        # control names, in creation order
        self.sets_focus = False
        self._read(node)

    def _read(self, node):
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "SetFocus":
                self.sets_focus = True
            if isinstance(func, ast.Attribute) and func.attr == "__init__":
                title = _keyword(child, "title")
                if title is not None:
                    self.title = _string_of(title)
                continue
            if not (isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "wx"):
                continue
            control = func.attr
            if control not in SELF_LABELLING | NEEDS_A_LABEL:
                continue
            self.controls.append(control)
            label = _keyword(child, "label")
            # A label built at run time reads as None here but is still a
            # label; only a missing one is a fault.
            text = _string_of(label) if label is not None else None
            if label is not None and text is None:
                text = "<dynamic>"
            if control in SELF_LABELLING:
                # A button created from a standard id (wx.ID_CANCEL) gets its
                # label and accelerator from wx itself.
                standard = any(
                    isinstance(arg, ast.Attribute) and arg.attr.startswith("ID_")
                    for arg in child.args)
                if text is not None or not standard:
                    self.labels.append((control, text))

    @property
    def accelerators(self):
        found = []
        for _control, text in self.labels:
            if not text:
                continue
            for match in re.finditer(r"&(.)", text):
                letter = match.group(1)
                if letter != "&":
                    found.append(letter.lower())
        return found

    @property
    def unlabelled_inputs(self):
        return [c for c in self.controls if c in NEEDS_A_LABEL]

    @property
    def static_texts(self):
        return [c for c in self.controls if c == "StaticText"]


def _dialogs():
    with open(UI_SOURCE, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=UI_SOURCE)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Attribute) and base.attr == "Dialog":
                found.append(Dialog(node))
    return found


DIALOGS = _dialogs()
NAMES = [d.name for d in DIALOGS]


def test_every_dialog_was_found():
    """A dialog missing from this list is a dialog nothing here checks."""
    assert set(NAMES) == {
        "VoiceBrowserDialog",
        "ImportVoicesDialog",
        "LexiconDialog",
        "PronunciationEntryDialog",
        "LanguageVoicesDialog",
        "PreparedAudioDialog",
        "DownloadSeveralDialog",
        "SettingsFilesDialog",
    }


@pytest.mark.parametrize("dialog", DIALOGS, ids=NAMES)
def test_dialog_has_a_title(dialog):
    """The title is the first thing a screen reader announces."""
    assert dialog.title, "%s has no title" % dialog.name


@pytest.mark.parametrize("dialog", DIALOGS, ids=NAMES)
def test_dialog_puts_focus_somewhere(dialog):
    """Without an explicit SetFocus, where focus lands is up to wx."""
    assert dialog.sets_focus, "%s never calls SetFocus" % dialog.name


@pytest.mark.parametrize("dialog", DIALOGS, ids=NAMES)
def test_every_control_has_a_label(dialog):
    for control, text in dialog.labels:
        assert text, "%s has a %s with no label" % (dialog.name, control)


@pytest.mark.parametrize("dialog", DIALOGS, ids=NAMES)
def test_accelerators_do_not_collide(dialog):
    """Two controls sharing an accelerator means one of them cannot be
    reached by keyboard."""
    letters = dialog.accelerators
    duplicates = sorted({l for l in letters if letters.count(l) > 1})
    assert not duplicates, "%s reuses accelerator(s) %s" % (
        dialog.name, ", ".join(duplicates))


@pytest.mark.parametrize("dialog", DIALOGS, ids=NAMES)
def test_accelerators_are_on_a_letter(dialog):
    """`&` before a space or at the end marks nothing."""
    for _control, text in dialog.labels:
        if not text:
            continue
        for match in re.finditer(r"&(.?)", text):
            letter = match.group(1)
            assert letter and (letter.isalnum() or letter == "&"), (
                "%s has an accelerator on %r in %r"
                % (dialog.name, letter, text))


@pytest.mark.parametrize("dialog", DIALOGS, ids=NAMES)
def test_input_controls_have_something_to_label_them(dialog):
    """A text field or list needs a StaticText; it has no label of its own."""
    inputs = dialog.unlabelled_inputs
    if not inputs:
        return
    assert len(dialog.static_texts) >= len(inputs), (
        "%s has %d controls needing a label and %d static texts"
        % (dialog.name, len(inputs), len(dialog.static_texts)))
