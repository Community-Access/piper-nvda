"""Stub of NVDA's config.conf with just enough behavior for the driver."""


class _Speech(dict):
    def __init__(self):
        super().__init__()
        self["autoLanguageSwitching"] = True
        self["outputDevice"] = "default"
        self["piper"] = {}


conf = {"speech": _Speech()}
