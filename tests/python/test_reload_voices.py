"""reload_installed_voices: the live synth follows the voice manager.

Removing or adding voices in the manager must update the running driver,
including moving off a removed voice instead of speaking into a deleted
model file.
"""

import threading

import synthDrivers.piper as piper
from synthDrivers.piper import _voices


def _voice(key, lang="en_US"):
    return _voices.InstalledVoice(
        key=key, display_name=key, language=lang, espeak_lang="en-us",
        num_speakers=1, speaker_id_map={})


def _driver(installed):
    d = piper.SynthDriver.__new__(piper.SynthDriver)
    d._voices = installed
    d._voice_by_key = {v.key: v for v in installed}
    d._voice = installed[0].key if installed else ""
    d._variant = "0"
    d._lock = threading.Lock()
    d.applied = []
    d.saved = []
    d.warmed = []
    d._apply_voice_settings = d.applied.append
    d._save_voice_settings = lambda: d.saved.append(True)
    d._request_warmup = lambda: d.warmed.append(True)
    return d


def test_reload_picks_up_new_voices(monkeypatch):
    d = _driver([_voice("en_US-a")])
    monkeypatch.setattr(_voices, "load_installed",
                        lambda: [_voice("en_US-a"), _voice("en_US-b")])
    d.reload_installed_voices()
    assert set(d._voice_by_key) == {"en_US-a", "en_US-b"}
    assert d._voice == "en_US-a"  # unchanged: it still exists
    assert d.applied == []        # no forced re-apply for a mere addition
    assert d.warmed


def test_reload_moves_off_a_removed_voice(monkeypatch):
    d = _driver([_voice("en_US-a"), _voice("en_US-b")])
    d._voice = "en_US-b"
    monkeypatch.setattr(_voices, "load_installed",
                        lambda: [_voice("en_US-a")])
    d.reload_installed_voices()
    assert d._voice == "en_US-a"
    assert d.applied == ["en_US-a"]
    assert d.saved == [True]
    assert d.warmed


def test_reload_with_nothing_left_keeps_going(monkeypatch):
    d = _driver([_voice("en_US-a")])
    monkeypatch.setattr(_voices, "load_installed", lambda: [])
    d.reload_installed_voices()
    assert d._voice_by_key == {}
    # Nothing to switch to; the driver just reports what it has.
    assert d.applied == []
