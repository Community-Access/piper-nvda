"""Stub of NVDA's synthDriverHandler for tests."""

from autoSettingsUtils.driverSetting import (
    BooleanDriverSetting,
    DriverSetting,
    NumericDriverSetting,
)


class VoiceInfo:
    def __init__(self, id, displayName, language=None):
        self.id = id
        self.displayName = displayName
        self.language = language


class _Action:
    def __init__(self):
        self.handlers = []

    def register(self, h):
        self.handlers.append(h)

    def notify(self, **kwargs):
        for h in list(self.handlers):
            h(**kwargs)


synthIndexReached = _Action()
synthDoneSpeaking = _Action()


class SynthDriver:
    name = ""
    description = ""
    supportedSettings = ()

    def __init__(self):
        pass

    def terminate(self):
        pass

    @classmethod
    def VoiceSetting(cls):
        return DriverSetting("voice", "Voice", availableInSettingsRing=True)

    @classmethod
    def VariantSetting(cls):
        return DriverSetting("variant", "Variant", availableInSettingsRing=True)

    @classmethod
    def RateSetting(cls):
        return NumericDriverSetting("rate", "Rate", availableInSettingsRing=True)

    @classmethod
    def RateBoostSetting(cls):
        return BooleanDriverSetting("rateBoost", "Rate boost")

    @classmethod
    def PitchSetting(cls):
        return NumericDriverSetting("pitch", "Pitch", availableInSettingsRing=True)

    @classmethod
    def InflectionSetting(cls):
        return NumericDriverSetting("inflection", "Inflection")

    @classmethod
    def VolumeSetting(cls):
        return NumericDriverSetting("volume", "Volume", availableInSettingsRing=True)

    @classmethod
    def _getConfigSpecForSettings(cls, settings):
        # Mirrors NVDA's AutoSettings._getConfigSpecForSettings.
        return {s.id: s.configSpec for s in settings if s.useConfig}
