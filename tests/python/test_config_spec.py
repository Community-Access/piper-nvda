"""Regression test: the driver must register its config spec before reading.

NVDA installs a synth driver's config spec in initSettings, which runs after
__init__. NVDA's config.AggregatedSection.__getitem__ permanently caches a
KeyError for a key that is missing from both the ini and the spec, so a
pre-spec read of a not-yet-saved setting (as _load_conf does in __init__)
poisons the cache, and NVDA's loadSettings then raises that KeyError and the
whole driver fails to load. Seen in the wild as:

    setSynth failed for piper ... KeyError: 'sentencePause'

the first launch after a new setting was added to an existing config section.
"""

import pytest

import synthDrivers.piper as piper


class FakeAggregatedSection:
    """NVDA's config.AggregatedSection, reduced to the behavior under test.

    Mirrors NVDA 2026.1 config/__init__.py AggregatedSection.__getitem__:
    - a hit is served from the cache, including a cached KeyError sentinel;
    - a key found in the profile (the ini) is returned and cached;
    - a key missing from the profile but present in the spec returns the
      spec default;
    - a key missing from both caches ``KeyError`` itself and raises, and
      every later read raises from that cache even if a spec arrives later.
    """

    def __init__(self, profile=None):
        self.profile = dict(profile or {})
        self.spec = {}
        self._cache = {}

    def __getitem__(self, key):
        try:
            val = self._cache[key]
        except KeyError:
            pass
        else:
            if val is KeyError:
                raise KeyError(key)
            return val
        if key in self.profile:
            val = self.profile[key]
            self._cache[key] = val
            return val
        if key in self.spec:
            val = self._default_from_spec(self.spec[key])
            self._cache[key] = val
            return val
        self._cache[key] = KeyError
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __setitem__(self, key, val):
        self.profile[key] = val
        self._cache[key] = val

    @staticmethod
    def _default_from_spec(spec_string):
        import re
        raw = re.search(r"default=([^,)]+)", spec_string).group(1)
        if raw in ("True", "False"):
            return raw == "True"
        try:
            return int(raw)
        except ValueError:
            return raw


# The keys __init__ reads plus the ones NVDA's loadSettings reads raw.
ALL_SETTING_KEYS = (
    "rate", "rateBoost", "pitch", "volume", "variant",
    "sentencePause", "rememberPerVoice", "useCache", "advancedMode",
    "variance", "noiseScale", "noiseW", "lengthScale",
)


def test_fake_section_reproduces_nvda_poisoning():
    """Sanity check of the fake: this is the NVDA behavior the fix targets."""
    section = FakeAggregatedSection({"voice": "x"})
    assert section.get("sentencePause", 25) == 25  # pre-spec read, poisons
    section.spec["sentencePause"] = "integer(default=25,min=0,max=100)"
    with pytest.raises(KeyError):
        section["sentencePause"]  # what NVDA's loadSettings does


@pytest.fixture
def section(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPER_DATA_DIR", str(tmp_path))
    import config
    # An old section that predates every 1.0.0 setting.
    sec = FakeAggregatedSection({"voice": "en_US-lessac-medium", "volume": 90})
    monkeypatch.setitem(config.conf["speech"], "piper", sec)
    return sec


def test_registered_spec_prevents_load_failure(section):
    d = piper.SynthDriver.__new__(piper.SynthDriver)
    d._register_config_spec()
    # What __init__ does next:
    assert d._load_conf("sentencePause", 25) == 25
    # What NVDA's loadSettings does afterwards: raw reads must not raise.
    for key in ALL_SETTING_KEYS:
        section[key]


def test_spec_covers_advanced_settings_while_hidden(section):
    """The advanced parameters need spec entries even when the simple mode
    hides them, or turning advanced mode on would hit the same KeyError."""
    d = piper.SynthDriver.__new__(piper.SynthDriver)
    d._register_config_spec()
    for key in ("noiseScale", "noiseW", "lengthScale"):
        assert key in section.spec


def test_register_config_spec_survives_missing_section(monkeypatch, tmp_path):
    """First ever run: no [[piper]] section. initSettings creates it later;
    registering must simply do nothing rather than raise."""
    monkeypatch.setenv("PIPER_DATA_DIR", str(tmp_path))
    import config
    monkeypatch.delitem(config.conf["speech"], "piper")
    d = piper.SynthDriver.__new__(piper.SynthDriver)
    d._register_config_spec()  # must not raise
