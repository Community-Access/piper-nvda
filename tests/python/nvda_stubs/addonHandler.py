"""Stub of addonHandler: initTranslation just guarantees a gettext `_`.

NVDA's real initTranslation binds the add-on's own catalog into the calling
module; outside NVDA an identity function keeps the modules importable.
"""

import builtins


def initTranslation():
    if not hasattr(builtins, "_"):
        builtins._ = lambda s: s
