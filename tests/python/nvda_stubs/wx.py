"""Minimal wx stub.

The voice manager cannot be driven headlessly, but its module must still be
importable in tests so that a missing import, a typo in a name used at module
scope, or a class that no longer exists is caught rather than waiting to fail
inside NVDA. Anything not defined here resolves to a permissive placeholder.
"""


class _Any:
    """Stands in for any wx constant, function, or widget."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Any()

    def __getattr__(self, name):
        return _Any()

    def __or__(self, other):
        return self

    def __ror__(self, other):
        return self

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


class Dialog:
    """Base class for the add-on's dialogs."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _Any()


def __getattr__(name):
    return _Any()
