"""Minimal stand-ins for NVDA speech commands used by the driver.

The prosody commands expose a settable `newValue` (in NVDA it is computed from
config); tests pass the absolute 0-100 value directly.
"""


class IndexCommand:
    def __init__(self, index):
        self.index = index


class CharacterModeCommand:
    def __init__(self, state):
        self.state = state
        self.isDefault = not state


class LangChangeCommand:
    def __init__(self, lang):
        self.lang = lang
        self.isDefault = not lang


class BreakCommand:
    def __init__(self, time=0):
        self.time = time


class _Prosody:
    def __init__(self, newValue=50):
        self.newValue = newValue
        self.isDefault = False


class PitchCommand(_Prosody):
    pass


class RateCommand(_Prosody):
    pass


class VolumeCommand(_Prosody):
    pass
