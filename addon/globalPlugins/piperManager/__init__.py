"""Global plugin adding a Tools menu entry to browse, download, and demo
Piper voices at any time."""

import gui
import wx
from logHandler import log

import globalPluginHandler


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
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
        try:
            from synthDrivers.piper._manager_ui import open_manager
        except Exception:
            log.exception("piper: manager unavailable")
            return
        open_manager()

    def terminate(self):
        try:
            if self._menuItem is not None:
                gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self._menuItem)
        except Exception:
            pass
        super().terminate()
