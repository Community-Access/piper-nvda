"""Install/uninstall hooks. Voices download at runtime, so onInstall is
empty. onUninstall optionally removes downloaded voices and cache."""

import os
import shutil


def onUninstall():
    import globalVars
    data_dir = os.path.join(globalVars.appArgs.configPath, "piper")
    if not os.path.isdir(data_dir):
        return
    try:
        import gui
        import wx
        result = gui.messageBox(
            # Translators: asked on uninstall.
            _("Also delete downloaded Piper voices and cache?"),
            _("Piper Neural Voices"),
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if result == wx.YES:
            shutil.rmtree(data_dir, ignore_errors=True)
    except Exception:
        pass
