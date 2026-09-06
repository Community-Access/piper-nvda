"""Stub driver-setting classes matching the attributes the driver relies on."""


class DriverSetting:
    def __init__(self, id, displayName, availableInSettingsRing=False,
                 defaultVal=None, **kwargs):
        self.id = id
        self.displayName = displayName
        self.availableInSettingsRing = availableInSettingsRing
        self.defaultVal = defaultVal
        self.useConfig = kwargs.get("useConfig", True)

    @property
    def configSpec(self):
        # Mirrors NVDA's DriverSetting.configSpec.
        return "string(default={})".format(self.defaultVal)


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

    @property
    def configSpec(self):
        return "integer(default={},min={},max={})".format(
            self.defaultVal, self.minVal, self.maxVal)


class BooleanDriverSetting(DriverSetting):
    def __init__(self, id, displayName, availableInSettingsRing=False,
                 defaultVal=False, **kwargs):
        super().__init__(id, displayName, availableInSettingsRing, defaultVal,
                         **kwargs)

    @property
    def configSpec(self):
        return "boolean(default={})".format(self.defaultVal)
