"""The global plugin must import and expose its commands.

Gestures are the part of an add-on a user binds themselves, so the scripts
have to exist, be in a named category, and carry the description NVDA shows
in the Input Gestures dialog.
"""

import pytest


@pytest.fixture(scope="module")
def plugin_module():
    import globalPlugins.piperManager as module
    return module


@pytest.mark.parametrize("name", [
    "script_openVoiceManager",
    "script_nextFavoriteVoice",
    "script_togglePreparedAudio",
])
def test_commands_are_available_to_bind(plugin_module, name):
    script = getattr(plugin_module.GlobalPlugin, name)
    assert script.description, "%s has no description for Input Gestures" % name
    assert script.category == plugin_module.CATEGORY


def test_commands_are_unassigned_by_default(plugin_module):
    """Choosing keys for the user risks clashing with something they use."""
    assert not getattr(plugin_module.GlobalPlugin, "_GlobalPlugin__gestures", {})


def test_piper_synth_is_none_when_another_synth_is_active(plugin_module,
                                                          monkeypatch):
    class Other:
        name = "espeak"

    import synthDriverHandler
    monkeypatch.setattr(synthDriverHandler, "getSynth", lambda: Other(),
                        raising=False)
    assert plugin_module._piper_synth() is None


def test_piper_synth_is_found_when_piper_is_active(plugin_module, monkeypatch):
    class Piper:
        name = "piper"

    import synthDriverHandler
    piper = Piper()
    monkeypatch.setattr(synthDriverHandler, "getSynth", lambda: piper,
                        raising=False)
    assert plugin_module._piper_synth() is piper
