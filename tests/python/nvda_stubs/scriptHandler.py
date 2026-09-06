"""Stub of NVDA's script decorator.

NVDA attaches the description and category to the function so they can be
listed in Input Gestures; the stub keeps them so tests can check they exist.
"""


def script(description="", category="", gesture=None, gestures=None, **kwargs):
    def decorate(func):
        func.__doc__ = description or func.__doc__
        func.category = category
        func.description = description
        return func

    return decorate
