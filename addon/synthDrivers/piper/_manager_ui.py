"""Voice browser: download Piper voices directly and hear demos.

The browser can play a voice's hosted demo sample before it is downloaded,
using its own short-lived helper process (independent of whichever synth is
active), so users can audition voices while using any synthesizer.
"""

import os
import tempfile
import threading
import urllib.request

import gui
import wx
from logHandler import log

try:
    import ui
except Exception:  # pragma: no cover
    ui = None

from . import _audio, _catalog, _download, _helperProc, _paths, _protocol as proto

_MB = 1024 * 1024


def _announce(message):
    if ui is not None:
        try:
            ui.message(message)
        except Exception:
            pass


def prompt_first_run():
    """Offer to open the voice browser when no voices are installed."""
    result = gui.messageBox(
        # Translators: shown when Piper has no voices yet.
        _("Piper has no voices installed yet. Open the voice manager to "
          "download voices now?"),
        _("Piper Neural Voices"),
        wx.YES_NO | wx.ICON_QUESTION,
    )
    if result != wx.YES:
        return False
    open_manager()
    # After the modal browser closes, report whether anything got installed.
    return bool(_paths.installed_voice_keys())


def open_manager():
    gui.mainFrame.prePopup()
    dlg = VoiceBrowserDialog(gui.mainFrame)
    dlg.ShowModal()
    dlg.Destroy()
    gui.mainFrame.postPopup()


class DemoPlayer:
    """A private helper + WavePlayer used only to play demo samples."""

    def __init__(self):
        self._helper = None
        self._pump = None
        self._player = None

    def _ensure(self):
        if self._helper is not None:
            return
        import nvwave
        try:
            self._player = nvwave.WavePlayer(
                channels=1, samplesPerSec=22050, bitsPerSample=16,
                wantDucking=True, purpose=nvwave.AudioPurpose.SPEECH)
        except (AttributeError, TypeError):
            self._player = nvwave.WavePlayer(
                channels=1, samplesPerSec=22050, bitsPerSample=16,
                wantDucking=True)
        self._pump = _audio.AudioPump(self._player, lambda i: None,
                                      lambda: None)
        self._helper = _helperProc.HelperProcess(
            _paths.HELPER_EXE,
            ["--espeak-dll", _paths.ESPEAK_DLL,
             "--espeak-data", _paths.ESPEAK_DATA,
             "--cache-dir", _paths.cache_dir()],
            on_frame=self._on_frame)
        self._helper.start()

    def _on_frame(self, msg_type, payload):
        if msg_type in (proto.AUDIO, proto.MARKER, proto.DONE):
            self._pump.handle_frame(msg_type, payload)

    def play_file(self, mp3_path):
        self._ensure()
        self._pump.cancel()
        try:
            self._helper.send(proto.CANCEL, {})
            self._helper.send(proto.PLAY_SAMPLE, {"path": mp3_path})
        except Exception:
            log.exception("piper: demo playback failed")

    def stop(self):
        if self._pump is not None:
            self._pump.cancel()
        if self._helper is not None:
            try:
                self._helper.send(proto.CANCEL, {})
            except Exception:
                pass

    def close(self):
        try:
            if self._helper is not None:
                self._helper.terminate()
            if self._pump is not None:
                self._pump.shutdown()
            if self._player is not None:
                self._player.close()
        except Exception:
            pass


class VoiceBrowserDialog(wx.Dialog):
    def __init__(self, parent):
        # Translators: title of the Piper voice browser.
        super().__init__(parent, title=_("Piper Voice Manager"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._demo = DemoPlayer()
        self._voices = []
        self._filtered = []

        main = wx.BoxSizer(wx.VERTICAL)

        # Language filter.
        filterRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: label for the language filter.
        filterRow.Add(wx.StaticText(self, label=_("&Language:")),
                      border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self._langChoice = wx.Choice(self, choices=[_("All languages")])
        self._langChoice.SetSelection(0)
        self._langChoice.Bind(wx.EVT_CHOICE, lambda e: self._refresh_list())
        filterRow.Add(self._langChoice, border=5, flag=wx.ALL)
        main.Add(filterRow, flag=wx.EXPAND)

        # Voice list.
        # Translators: label for the list of voices.
        main.Add(wx.StaticText(self, label=_("&Voices:")), border=5,
                 flag=wx.LEFT | wx.TOP)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE, size=(520, 300))
        self._list.Bind(wx.EVT_LISTBOX, lambda e: self._update_buttons())
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        # Buttons.
        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: play a voice demo.
        self._demoBtn = wx.Button(self, label=_("&Play demo"))
        self._demoBtn.Bind(wx.EVT_BUTTON, self._on_demo)
        # Translators: stop the demo.
        self._stopBtn = wx.Button(self, label=_("&Stop demo"))
        self._stopBtn.Bind(wx.EVT_BUTTON, lambda e: self._demo.stop())
        # Translators: download the selected voice.
        self._dlBtn = wx.Button(self, label=_("&Download"))
        self._dlBtn.Bind(wx.EVT_BUTTON, self._on_download)
        # Translators: remove an installed voice.
        self._rmBtn = wx.Button(self, label=_("&Remove"))
        self._rmBtn.Bind(wx.EVT_BUTTON, self._on_remove)
        # Translators: close the manager.
        closeBtn = wx.Button(self, wx.ID_CLOSE, label=_("&Close"))
        closeBtn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        for b in (self._demoBtn, self._stopBtn, self._dlBtn, self._rmBtn,
                  closeBtn):
            btns.Add(b, border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        self.SetSizerAndFit(main)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._list.SetFocus()

        self._load_catalog_async()

    # -- catalog loading ---------------------------------------------------

    def _load_catalog_async(self):
        _announce(_("Loading Piper voice list"))

        def worker():
            try:
                _catalog.download_catalog()
            except Exception:
                log.exception("piper: catalog download failed")
            voices = _catalog.load_catalog()
            wx.CallAfter(self._on_catalog_loaded, voices)

        threading.Thread(target=worker, daemon=True).start()

    def _on_catalog_loaded(self, voices):
        self._voices = voices
        langs = sorted({v.lang_english for v in voices if v.lang_english})
        self._langChoice.Set([_("All languages")] + langs)
        self._langChoice.SetSelection(0)
        self._refresh_list()
        if voices:
            _announce(_("{count} voices available").format(count=len(voices)))
        else:
            _announce(_("Could not load the voice list. Check your internet "
                        "connection."))

    def _refresh_list(self):
        sel_lang = None
        idx = self._langChoice.GetSelection()
        if idx > 0:
            sel_lang = self._langChoice.GetString(idx)
        self._filtered = [
            v for v in self._voices
            if sel_lang is None or v.lang_english == sel_lang
        ]
        labels = []
        for v in self._filtered:
            # Translators: {status} is Installed or blank.
            status = _(" [installed]") if v.installed else ""
            size = (" - %d MB" % round(v.model_size / _MB)
                    if v.model_size else "")
            labels.append(v.display_name + size + status)
        self._list.Set(labels)
        if labels:
            self._list.SetSelection(0)
        self._update_buttons()

    def _selected_voice(self):
        i = self._list.GetSelection()
        if i == wx.NOT_FOUND or i >= len(self._filtered):
            return None
        return self._filtered[i]

    def _update_buttons(self):
        v = self._selected_voice()
        has = v is not None
        self._dlBtn.Enable(has and not v.installed)
        self._rmBtn.Enable(has and v.installed)
        self._demoBtn.Enable(has)

    # -- actions -----------------------------------------------------------

    def _on_demo(self, evt):
        v = self._selected_voice()
        if v is None:
            return
        _announce(_("Loading demo"))

        def worker():
            try:
                data = urllib.request.urlopen(v.sample_url()).read()
                tmp = os.path.join(tempfile.gettempdir(),
                                   "piper_demo_%s.mp3" % v.key)
                with open(tmp, "wb") as f:
                    f.write(data)
                wx.CallAfter(self._demo.play_file, tmp)
            except Exception:
                log.exception("piper: demo fetch failed")
                wx.CallAfter(_announce, _("Demo unavailable for this voice"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download(self, evt):
        v = self._selected_voice()
        if v is None or v.installed:
            return
        if _download_voice_with_progress(self, v):
            self._refresh_list()

    def _on_remove(self, evt):
        v = self._selected_voice()
        if v is None or not v.installed:
            return
        _download.remove_voice(v.key)
        _announce(_("Removed {name}").format(name=v.name))
        self._refresh_list()

    def _on_close(self, evt):
        self._demo.close()
        evt.Skip()


def _download_voice_with_progress(parent, voice):
    total = voice.model_size or 1
    dlg = wx.ProgressDialog(
        # Translators: download dialog title.
        _("Downloading voice"),
        # Translators: {name} is the voice name.
        _("Downloading {name}...").format(name=voice.display_name),
        maximum=100, parent=parent,
        style=wx.PD_CAN_ABORT | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
        | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)
    state = {"done": 0, "total": total, "error": None, "cancel": False,
             "finished": False, "last": -1}

    def worker():
        try:
            _download.download_voice(
                voice,
                progress=lambda d, t: state.update(done=d, total=t or total),
                should_cancel=lambda: state["cancel"])
        except _download.Cancelled:
            state["error"] = "cancelled"
        except Exception as e:
            log.exception("piper: voice download failed")
            state["error"] = str(e)
        finally:
            state["finished"] = True

    threading.Thread(target=worker, daemon=True).start()
    while not state["finished"]:
        wx.MilliSleep(100)
        pct = int(state["done"] * 100 / max(1, state["total"]))
        keep, _s = dlg.Update(min(pct, 99),
                              _("Downloaded {pct}%").format(pct=pct))
        if not keep:
            state["cancel"] = True
        milestone = pct - (pct % 20)
        if milestone != state["last"] and pct < 100:
            state["last"] = milestone
            _announce(_("Download {pct} percent").format(pct=milestone))
        wx.Yield()
    dlg.Update(100)
    dlg.Destroy()

    if state["error"] == "cancelled":
        _announce(_("Download cancelled"))
        return False
    if state["error"]:
        gui.messageBox(
            _("The download failed: {error}").format(error=state["error"]),
            _("Piper Neural Voices"), wx.OK | wx.ICON_ERROR)
        return False
    _announce(_("Installed {name}").format(name=voice.name))
    return True
