"""Stub of the parts of NVDA's gui module the add-on touches."""


class _MainFrame:
    def prePopup(self):
        pass

    def postPopup(self):
        pass


mainFrame = _MainFrame()

_messages = []


def messageBox(text, caption="", style=0, parent=None):
    """Record instead of showing; tests assert on what would be displayed."""
    _messages.append((text, caption))
    return 0
