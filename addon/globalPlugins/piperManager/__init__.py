"""Global plugin: the Tools menu entry and the add-on's gestures.

The gestures are unassigned by default. NVDA lists them under "Piper Neural
Voices" in Input Gestures, where anyone can bind the ones they want, which is
the convention users expect rather than a set of keys chosen for them that may
clash with something else.
"""

import gui
import wx
from logHandler import log
from scriptHandler import script

import globalPluginHandler
import ui

try:
    import addonHandler
    addonHandler.initTranslation()
except Exception:  # pragma: no cover - outside NVDA (tests, tools)
    import builtins
    if not hasattr(builtins, "_"):
        builtins._ = lambda s: s

# Translators: the category the add-on's commands appear under in NVDA's
# Input Gestures dialog.
CATEGORY = _("Piper Neural Voices")


def _piper_synth():
    """The running Piper synthesizer, or None if another one is active."""
    try:
        import synthDriverHandler
        synth = synthDriverHandler.getSynth()
    except Exception:
        return None
    return synth if getattr(synth, "name", None) == "piper" else None


def _needs_piper():
    ui.message(
        # Translators: spoken when a Piper command is used with another synth.
        _("Piper Neural Voices is not the current synthesizer"))


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = CATEGORY

    def __init__(self):
        super().__init__()
        self._menuItem = None
        try:
            toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
            self._menuItem = toolsMenu.Append(
                wx.ID_ANY,
                # Translators: Tools menu item opening the Piper voice manager.
                _("Piper voice manager..."),
            )
            gui.mainFrame.sysTrayIcon.Bind(
                wx.EVT_MENU, self._on_manager, self._menuItem)
        except Exception:
            log.exception("piper: could not add Tools menu item")

    def _on_manager(self, evt):
        self._open_manager()

    def _open_manager(self):
        try:
            from synthDrivers.piper._manager_ui import open_manager
        except Exception:
            log.exception("piper: manager unavailable")
            return
        open_manager()

    @script(
        # Translators: description of a command, shown in Input Gestures.
        description=_("Opens the Piper voice manager"),
        category=CATEGORY,
    )
    def script_openVoiceManager(self, gesture):
        self._open_manager()

    @script(
        # Translators: description of a command, shown in Input Gestures.
        description=_("Moves to the next favourite Piper voice"),
        category=CATEGORY,
    )
    def script_nextFavoriteVoice(self, gesture):
        synth = _piper_synth()
        if synth is None:
            _needs_piper()
            return
        name = synth.next_favorite_voice()
        if name is None:
            ui.message(
                # Translators: spoken when there is nowhere to switch to.
                _("Only one Piper voice is installed"))
        else:
            ui.message(name)

    @script(
        # Translators: description of a command, shown in Input Gestures.
        description=_("Turns background preparation of Piper audio on or off"),
        category=CATEGORY,
    )
    def script_togglePreparedAudio(self, gesture):
        synth = _piper_synth()
        if synth is None:
            _needs_piper()
            return
        if synth.toggle_cache():
            # Translators: spoken when background preparation is switched on.
            ui.message(_("Preparing audio in the background"))
        else:
            # Translators: spoken when background preparation is switched off.
            ui.message(_("Not preparing audio in the background"))

    def terminate(self):
        try:
            if self._menuItem is not None:
                gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self._menuItem)
        except Exception:
            pass
        super().terminate()
