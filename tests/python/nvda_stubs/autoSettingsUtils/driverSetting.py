"""Stub driver-setting classes matching the attributes the driver relies on."""


class DriverSetting:
    def __init__(self, id, displayName, availableInSettingsRing=False,
                 defaultVal=None, **kwargs):
        self.id = id
        self.displayName = displayName
        self.availableInSettingsRing = availableInSettingsRing
        self.defaultVal = defaultVal
        self.useConfig = kwargs.get("useConfig", True)


class NumericDriverSetting(DriverSetting):
    def __init__(self, id, displayName, availableInSettingsRing=False,
                 defaultVal=50, minVal=0, maxVal=100, minStep=1,
                 normalStep=5, largeStep=10, **kwargs):
        super().__init__(id, displayName, availableInSettingsRing, defaultVal,
                         **kwargs)
        self.minVal = minVal
        self.maxVal = maxVal
        self.normalStep = normalStep
        self.largeStep = largeStep


class BooleanDriverSetting(DriverSetting):
    def __init__(self, id, displayName, availableInSettingsRing=False,
                 defaultVal=False, **kwargs):
        super().__init__(id, displayName, availableInSettingsRing, defaultVal,
                         **kwargs)
