"""The voice manager cannot be driven without a real wx, but it must import.

This catches the failure mode that would otherwise only show up in NVDA: a
module-level name that does not exist, a dialog removed from the file, or an
import that was dropped while editing.
"""

import pytest


@pytest.fixture(scope="module")
def manager():
    from synthDrivers.piper import _manager_ui
    return _manager_ui


@pytest.mark.parametrize("name", [
    "VoiceBrowserDialog",
    "ImportVoicesDialog",
    "LexiconDialog",
    "PronunciationEntryDialog",
    "LanguageVoicesDialog",
    "PreparedAudioDialog",
    "DemoPlayer",
    "open_manager",
    "prompt_first_run",
])
def test_manager_exposes(manager, name):
    assert hasattr(manager, name)


def test_notify_synth_is_quiet_when_piper_is_not_running(manager):
    # No synthesizer is active under the stubs; this must not raise, and it
    # reports that it reached nothing so callers can fall back.
    assert manager._notify_synth("reload_lexicon") is False


def test_notify_synth_calls_the_driver(manager, monkeypatch):
    calls = []

    class FakeSynth:
        name = "piper"

        def reload_lexicon(self):
            calls.append("reload_lexicon")

    import synthDriverHandler
    monkeypatch.setattr(synthDriverHandler, "getSynth", lambda: FakeSynth(),
                        raising=False)
    assert manager._notify_synth("reload_lexicon") is True
    assert calls == ["reload_lexicon"]


def test_notify_synth_ignores_other_synthesizers(manager, monkeypatch):
    class Other:
        name = "espeak"

        def reload_lexicon(self):
            raise AssertionError("must not be called")

    import synthDriverHandler
    monkeypatch.setattr(synthDriverHandler, "getSynth", lambda: Other(),
                        raising=False)
    assert manager._notify_synth("reload_lexicon") is False
