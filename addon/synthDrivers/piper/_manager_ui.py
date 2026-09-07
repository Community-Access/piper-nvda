"""Voice manager: browse and download Piper voices, hear demos, import
voices already on disk, edit pronunciations, and pin voices to languages.

Every dialog here can play audio through its own short-lived helper process,
independent of whichever synthesizer is active, so voices and pronunciation
fixes can be auditioned while using any synth.
"""

import os
import tempfile
import threading
import urllib.request

import addonHandler
import gui
import wx
from logHandler import log

addonHandler.initTranslation()

try:
    import ui
except Exception:  # pragma: no cover
    ui = None

try:
    # A plain wx.CheckListBox does not expose the checked state of its items
    # to a screen reader, so the checkboxes are silent and the list reads as
    # a plain list. NVDA's own replacement announces "checked" and
    # "not checked" on every item and announces the change when space
    # toggles one.
    from gui.nvdaControls import CustomCheckListBox as _CheckListBox
except Exception:  # pragma: no cover - outside NVDA (tests)
    _CheckListBox = wx.CheckListBox

from . import (
    _audio,
    _backup,
    _catalog,
    _download,
    _helperProc,
    _import,
    _langvoices,
    _lexicon,
    _paths,
    _protocol as proto,
    _voices,
    _voicesettings,
    _warmup,
)

_MB = 1024 * 1024


def _announce(message):
    if ui is not None:
        try:
            ui.message(message)
        except Exception:
            pass


def _set_list(listbox, labels):
    """Fill a list box, giving an empty one a single placeholder row.

    A focused wx.ListBox with no rows is announced by NVDA as "unknown"; a
    placeholder row reads as what it is. Callers already treat a selection
    index at or beyond their own row count as no selection, so the
    placeholder enables no buttons.
    """
    if labels:
        listbox.Set(labels)
    else:
        # Translators: the only row of a list that has nothing in it.
        listbox.Set([_("No entries")])
        listbox.SetSelection(0)


def _recommended_voice():
    """The voice to offer on a first run, for NVDA's own language."""
    try:
        import languageHandler
        language = languageHandler.getLanguage()
    except Exception:
        language = "en"
    try:
        _catalog.download_catalog()
    except Exception:
        log.exception("piper: catalog download failed")
    return _catalog.recommend(_catalog.load_catalog(), language)


def prompt_first_run():
    """Offer a voice when none are installed.

    Someone whose synthesizer has no voice wants speech, not a catalogue of
    176 of them, so offer the best match for their language directly and keep
    the browser as the alternative.
    """
    _announce(_("Looking for a voice for your language"))
    voice = _recommended_voice()
    if voice is not None:
        result = gui.messageBox(
            # Translators: {name} is a voice, {size} its size in megabytes.
            _("Piper has no voices installed yet. Download {name}, "
              "{size} MB, now?\n\n"
              "Choose No to pick a different voice yourself.").format(
                  name=voice.display_name,
                  size=round((voice.model_size or 0) / _MB)),
            _("Piper Neural Voices"),
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if result == wx.YES:
            if _download_voice_with_progress(gui.mainFrame, voice):
                return bool(_paths.installed_voice_keys())
            return False
    else:
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


def _notify_synth(method):
    """Ask the running Piper synthesizer to pick up changed settings.

    Returns whether it was reached. Nothing happens when another synthesizer
    is active; the new files are read the next time Piper starts.
    """
    try:
        import synthDriverHandler
        synth = synthDriverHandler.getSynth()
    except Exception:
        return False
    if synth is None or getattr(synth, "name", None) != "piper":
        return False
    try:
        getattr(synth, method)()
    except Exception:
        log.exception("piper: %s failed", method)
        return False
    return True


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
             # No cache dir: demos gain nothing from one, and sharing the
             # live synthesizer's cache would let two processes overwrite
             # each other's prepared audio.
             ],
            on_frame=self._on_frame)
        self._helper.start()

    def _on_frame(self, msg_type, payload):
        if msg_type in (proto.AUDIO, proto.MARKER, proto.DONE):
            self._pump.handle_frame(msg_type, payload)

    def speak_text(self, model_path, text, lexicon=None):  # noqa: D401
        """Synthesize `text` with a voice, optionally under a draft lexicon.

        Used to audition a pronunciation before it is saved, so the user can
        hear the change rather than trusting the IPA they typed.
        """
        self._ensure()
        self._pump.cancel()
        try:
            self._helper.send(proto.CANCEL, {})
            if lexicon is not None:
                rev, entries = lexicon
                self._helper.send(proto.SET_LEXICON,
                                  _lexicon.message(rev, entries))
            self._helper.send(proto.SPEAK, {
                "utteranceId": 1,
                "segments": [{"text": text, "modelPath": model_path}],
                "indexesAfter": [],
            })
        except Exception:
            log.exception("piper: preview failed")

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
        self._settings, self._favorites = _voicesettings.load()

        main = wx.BoxSizer(wx.VERTICAL)

        # Language and quality filters.
        filterRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: label for the language filter.
        filterRow.Add(wx.StaticText(self, label=_("&Language:")),
                      border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self._langChoice = wx.Choice(self, choices=[_("All languages")])
        self._langChoice.SetSelection(0)
        self._langChoice.Bind(wx.EVT_CHOICE, lambda e: self._refresh_list())
        filterRow.Add(self._langChoice, border=5, flag=wx.ALL)
        # Translators: label for the quality filter.
        filterRow.Add(wx.StaticText(self, label=_("&Quality:")),
                      border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self._qualityChoice = wx.Choice(self, choices=[_("All qualities")])
        self._qualityChoice.SetSelection(0)
        self._qualityChoice.Bind(wx.EVT_CHOICE, lambda e: self._refresh_list())
        filterRow.Add(self._qualityChoice, border=5, flag=wx.ALL)
        main.Add(filterRow, flag=wx.EXPAND)

        # Searching is faster than filtering when you know what you want, and
        # there are 176 voices.
        searchRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: label for the voice search field.
        searchRow.Add(wx.StaticText(self, label=_("&Search:")),
                      border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self._search = wx.TextCtrl(self, size=(220, -1))
        self._search.Bind(wx.EVT_TEXT, lambda e: self._refresh_list())
        searchRow.Add(self._search, border=5, flag=wx.ALL)
        # Translators: checkbox limiting the list to downloaded voices.
        self._installedOnly = wx.CheckBox(self, label=_("&Installed only"))
        self._installedOnly.Bind(wx.EVT_CHECKBOX, lambda e: self._refresh_list())
        searchRow.Add(self._installedOnly, border=5,
                      flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        main.Add(searchRow, flag=wx.EXPAND)

        # Voice list.
        # Translators: label for the list of voices.
        main.Add(wx.StaticText(self, label=_("&Voices:")), border=5,
                 flag=wx.LEFT | wx.TOP)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE, size=(520, 300))
        self._list.Bind(wx.EVT_LISTBOX, lambda e: self._update_buttons())
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        # Buttons acting on the selected voice.
        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: play a voice demo.
        self._demoBtn = wx.Button(self, label=_("&Play demo"))
        self._demoBtn.Bind(wx.EVT_BUTTON, self._on_demo)
        # Translators: stop the demo.
        self._stopBtn = wx.Button(self, label=_("St&op demo"))
        self._stopBtn.Bind(wx.EVT_BUTTON, lambda e: self._demo.stop())
        # One button that becomes Download or Remove depending on whether the
        # selected voice is installed.
        # Translators: download the selected voice.
        self._actionBtn = wx.Button(self, label=_("&Download"))
        self._actionBtn.Bind(wx.EVT_BUTTON, self._on_action)
        # Translators: marks a voice as one of your favourites.
        self._favBtn = wx.Button(self, label=_("&Favourite"))
        self._favBtn.Bind(wx.EVT_BUTTON, self._on_favorite)
        # Translators: opens the dialog for downloading several voices.
        severalBtn = wx.Button(self, label=_("Download s&everal..."))
        severalBtn.Bind(wx.EVT_BUTTON, self._on_download_several)
        for b in (self._demoBtn, self._stopBtn, self._actionBtn, self._favBtn,
                  severalBtn):
            btns.Add(b, border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        # Hearing a voice say your own words tells you more than a demo does.
        sampleRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: label for the field of text to speak as a sample.
        sampleRow.Add(wx.StaticText(self, label=_("Speak &text:")),
                      border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self._sample = wx.TextCtrl(self, size=(300, -1),
                                   style=wx.TE_PROCESS_ENTER)
        self._sample.Bind(wx.EVT_TEXT_ENTER, self._on_speak_sample)
        sampleRow.Add(self._sample, border=5, flag=wx.ALL)
        # Translators: speaks the text typed beside it.
        self._speakBtn = wx.Button(self, label=_("Spea&k"))
        self._speakBtn.Bind(wx.EVT_BUTTON, self._on_speak_sample)
        sampleRow.Add(self._speakBtn, border=4, flag=wx.ALL)
        main.Add(sampleRow, flag=wx.EXPAND)

        # Buttons for everything else the manager can do.
        tools = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: import voices installed by other add-ons.
        importBtn = wx.Button(self, label=_("I&mport voices..."))
        importBtn.Bind(wx.EVT_BUTTON, self._on_import)
        # Translators: install a voice from a file on this computer.
        fileBtn = wx.Button(self, label=_("I&nstall from file..."))
        fileBtn.Bind(wx.EVT_BUTTON, self._on_install_file)
        # Translators: edit how particular words are pronounced.
        lexBtn = wx.Button(self, label=_("Pron&unciations..."))
        lexBtn.Bind(wx.EVT_BUTTON, self._on_lexicon)
        # Translators: choose which voice each language uses.
        langBtn = wx.Button(self, label=_("Lan&guage voices..."))
        langBtn.Bind(wx.EVT_BUTTON, self._on_language_voices)
        # Translators: manage the audio prepared in advance for instant echo.
        audioBtn = wx.Button(self, label=_("Prepared &audio..."))
        audioBtn.Bind(wx.EVT_BUTTON, self._on_prepared_audio)
        # Translators: back up, restore, or reset the add-on's settings.
        backupBtn = wx.Button(self, label=_("&Back up or restore..."))
        backupBtn.Bind(wx.EVT_BUTTON, self._on_backup)
        # Translators: close the manager.
        closeBtn = wx.Button(self, wx.ID_CLOSE, label=_("&Close"))
        closeBtn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        for b in (importBtn, fileBtn, lexBtn, langBtn, audioBtn, backupBtn,
                  closeBtn):
            tools.Add(b, border=4, flag=wx.ALL)
        main.Add(tools, flag=wx.ALIGN_CENTER)

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

    # Order qualities from smallest/fastest to largest/best.
    _QUALITY_ORDER = ["x_low", "low", "medium", "high"]

    def _on_catalog_loaded(self, voices):
        self._voices = voices
        langs = sorted({v.lang_english for v in voices if v.lang_english})
        self._langChoice.Set([_("All languages")] + langs)
        self._langChoice.SetSelection(0)
        present = {v.quality for v in voices if v.quality}
        qualities = [q for q in self._QUALITY_ORDER if q in present]
        qualities += sorted(present - set(self._QUALITY_ORDER))
        self._qualities = qualities
        self._qualityChoice.Set([_("All qualities")] + qualities)
        self._qualityChoice.SetSelection(0)
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
        sel_quality = None
        qidx = self._qualityChoice.GetSelection()
        if qidx > 0:
            sel_quality = self._qualityChoice.GetString(qidx)
        search = self._search.GetValue().strip().lower()
        installed_only = self._installedOnly.GetValue()
        self._filtered = [
            v for v in self._voices
            if (sel_lang is None or v.lang_english == sel_lang)
            and (sel_quality is None or v.quality == sel_quality)
            and (not installed_only or v.installed)
            and (not search or search in v.display_name.lower()
                 or search in v.key.lower())
        ]
        labels = []
        for v in self._filtered:
            # Translators: shown after an installed voice's name.
            status = _(" [installed]") if v.installed else ""
            # Translators: shown after a voice marked as a favourite.
            favorite = _(" [favourite]") if v.key in self._favorites else ""
            size = (" - %d MB" % round(v.model_size / _MB)
                    if v.model_size else "")
            labels.append(v.display_name + size + status + favorite)
        _set_list(self._list, labels)
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
        self._demoBtn.Enable(has)
        self._actionBtn.Enable(has)
        self._favBtn.Enable(has and v.installed)
        if has and v.installed and v.key in self._favorites:
            # Translators: button that removes a voice from the favourites.
            self._favBtn.SetLabel(_("Remove &favourite"))
        else:
            # Translators: button that makes a voice a favourite.
            self._favBtn.SetLabel(_("&Favourite"))
        if has and v.installed:
            # Translators: button to remove the selected installed voice.
            self._actionBtn.SetLabel(_("&Remove"))
        else:
            # Translators: button to download the selected voice.
            self._actionBtn.SetLabel(_("&Download"))

    # -- actions -----------------------------------------------------------

    def _on_demo(self, evt):
        v = self._selected_voice()
        if v is None:
            return
        _announce(_("Loading demo"))

        def worker():
            try:
                data = urllib.request.urlopen(
                    v.sample_url(), timeout=_download.TIMEOUT).read()
                tmp = os.path.join(tempfile.gettempdir(),
                                   "piper_demo_%s.mp3" % v.key)
                with open(tmp, "wb") as f:
                    f.write(data)
                wx.CallAfter(self._demo.play_file, tmp)
            except Exception:
                log.exception("piper: demo fetch failed")
                wx.CallAfter(_announce, _("Demo unavailable for this voice"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_action(self, evt):
        v = self._selected_voice()
        if v is None:
            return
        if v.installed:
            _download.remove_voice(v.key)
            _announce(_("Removed {name}").format(name=v.name))
            _notify_synth("reload_installed_voices")
            self._refresh_list()
            self._keep_selection(v.key)
        else:
            if _download_voice_with_progress(self, v):
                _notify_synth("reload_installed_voices")
                self._refresh_list()
                self._keep_selection(v.key)

    def _preview_model(self):
        """Model path to use for pronunciation previews: the selected voice
        when it is installed, otherwise any installed voice."""
        voice = self._selected_voice()
        if voice is not None and voice.installed:
            return _paths.voice_model_path(voice.key)
        keys = _paths.installed_voice_keys()
        return _paths.voice_model_path(keys[0]) if keys else None

    def _on_import(self, evt):
        found = _import.discover()
        if not found:
            gui.messageBox(
                # Translators: shown when no other add-on's voices were found.
                _("No voices from other Piper add-ons were found. Sonata and "
                  "Dengjen voices are detected automatically when those "
                  "add-ons are installed."),
                _("Piper Neural Voices"), wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = ImportVoicesDialog(self, found)
        if dlg.ShowModal() == wx.ID_OK:
            _notify_synth("reload_installed_voices")
            self._refresh_list()
        dlg.Destroy()

    def _on_install_file(self, evt):
        dlg = wx.FileDialog(
            self,
            # Translators: title of the file picker for installing a voice.
            message=_("Choose a Piper voice archive or model"),
            # Translators: file types accepted when installing a voice.
            wildcard=_("Piper voices (*.tar.gz;*.onnx)|*.tar.gz;*.tgz;*.onnx"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        try:
            keys = _import.install_from_file(path)
        except Exception as e:
            log.exception("piper: install from file failed")
            gui.messageBox(
                # Translators: {error} explains why the file was rejected.
                _("That file could not be installed: {error}").format(error=e),
                _("Piper Neural Voices"), wx.OK | wx.ICON_ERROR, self)
            return
        _announce(_("Installed {count} voices").format(count=len(keys)))
        _notify_synth("reload_installed_voices")
        self._refresh_list()

    def _on_lexicon(self, evt):
        dlg = LexiconDialog(self, self._demo, self._preview_model())
        if dlg.ShowModal() == wx.ID_OK:
            _notify_synth("reload_lexicon")
        dlg.Destroy()

    def _on_language_voices(self, evt):
        installed = _voices.load_installed()
        if not installed:
            gui.messageBox(
                # Translators: shown when there are no voices to assign.
                _("Download at least one voice before assigning languages."),
                _("Piper Neural Voices"), wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = LanguageVoicesDialog(self, installed)
        if dlg.ShowModal() == wx.ID_OK:
            _notify_synth("reload_language_voices")
        dlg.Destroy()

    def _on_favorite(self, evt):
        """Add or remove the selected voice from the favourites ring."""
        voice = self._selected_voice()
        if voice is None:
            return
        if not voice.installed:
            gui.messageBox(
                # Translators: shown when marking a voice that is not there.
                _("Download this voice before making it a favourite."),
                _("Piper Neural Voices"), wx.OK | wx.ICON_INFORMATION, self)
            return
        if voice.key in self._favorites:
            self._favorites.remove(voice.key)
            # Translators: {name} is no longer a favourite.
            _announce(_("{name} removed from favourites").format(
                name=voice.name))
        else:
            self._favorites.append(voice.key)
            # Translators: {name} is now a favourite.
            _announce(_("{name} added to favourites").format(name=voice.name))
        self._save_favorites()
        self._refresh_list()
        self._keep_selection(voice.key)

    def _save_favorites(self):
        # Re-read the per-voice settings from disk: the live synthesizer may
        # have saved newer values while this dialog was open, and writing
        # the snapshot taken at construction would revert them.
        try:
            settings, _stale = _voicesettings.load()
            _voicesettings.save(settings, self._favorites)
        except OSError:
            log.exception("piper: saving favourites failed")
            return
        _notify_synth("reload_voice_settings")

    def _on_speak_sample(self, evt):
        """Speak whatever the user typed, in the voice they are looking at."""
        text = self._sample.GetValue().strip()
        model = self._preview_model()
        if not text or model is None:
            gui.messageBox(
                # Translators: shown when there is nothing to speak with.
                _("Type some text, and download a voice to hear it with."),
                _("Piper Neural Voices"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self._demo.speak_text(model, text)

    def _on_download_several(self, evt):
        """Queue up every voice the current filters show."""
        if not self._filtered:
            return
        dlg = DownloadSeveralDialog(self, self._filtered)
        dlg.ShowModal()
        dlg.Destroy()
        self._refresh_list()

    def _on_backup(self, evt):
        dlg = SettingsFilesDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_prepared_audio(self, evt):
        dlg = PreparedAudioDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            _notify_synth("reload_warmup_words")
        dlg.Destroy()

    def _keep_selection(self, voice_key):
        """Reselect a voice by key after the list is rebuilt, so focus stays
        on the item the user just acted on."""
        for i, voice in enumerate(self._filtered):
            if voice.key == voice_key:
                self._list.SetSelection(i)
                break
        self._update_buttons()

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


class ImportVoicesDialog(wx.Dialog):
    """Copy voices installed by Sonata or Dengjen into this add-on.

    The other add-ons keep ordinary Piper `.onnx` models on disk, so switching
    is a file copy rather than a fresh multi-gigabyte download.
    """

    def __init__(self, parent, voices):
        # Translators: title of the import dialog.
        super().__init__(parent, title=_("Import voices from other add-ons"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._voices = voices
        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: label for the list of importable voices.
        main.Add(wx.StaticText(self, label=_("&Voices found on this computer:")),
                 border=5, flag=wx.ALL)
        labels = []
        for voice in voices:
            if voice.installed:
                # Translators: {name} is a voice, {source} the add-on it came
                # from; this voice is already installed here.
                labels.append(_("{name} (from {source}) - already installed")
                              .format(name=voice.key, source=voice.source))
            else:
                # Translators: {name} is a voice, {source} the add-on it came
                # from, {size} its size in megabytes.
                labels.append(_("{name} (from {source}) - {size} MB").format(
                    name=voice.key, source=voice.source,
                    size=round(voice.size / _MB)))
        self._list = _CheckListBox(self, choices=labels, size=(520, 260))
        for i, voice in enumerate(voices):
            self._list.Check(i, not voice.installed)
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: button that copies the checked voices.
        importBtn = wx.Button(self, wx.ID_OK, label=_("&Import"))
        importBtn.Bind(wx.EVT_BUTTON, self._on_import)
        cancelBtn = wx.Button(self, wx.ID_CANCEL)
        btns.Add(importBtn, border=4, flag=wx.ALL)
        btns.Add(cancelBtn, border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        self.SetSizerAndFit(main)
        self._list.SetFocus()

    def _on_import(self, evt):
        chosen = [self._voices[i] for i in self._list.GetCheckedItems()]
        if not chosen:
            self.EndModal(wx.ID_CANCEL)
            return
        try:
            keys = _import.import_voices(chosen)
        except Exception as e:
            log.exception("piper: voice import failed")
            gui.messageBox(
                # Translators: {error} explains why importing stopped.
                _("Importing failed: {error}").format(error=e),
                _("Piper Neural Voices"), wx.OK | wx.ICON_ERROR, self)
            return
        # Translators: {count} voices were copied in.
        _announce(_("Imported {count} voices").format(count=len(keys)))
        self.EndModal(wx.ID_OK)


class LexiconDialog(wx.Dialog):
    """Edit whole-word pronunciation overrides given as IPA phonemes.

    espeak-ng guesses the pronunciation of every word for the voice, and it
    guesses names, acronyms, and loan words wrong fairly often. An entry here
    replaces its guess, and can be auditioned before it is saved.
    """

    def __init__(self, parent, demo, preview_model):
        # Translators: title of the pronunciation dialog.
        super().__init__(parent, title=_("Pronunciations"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._demo = demo
        self._preview_model = preview_model
        self._rev, entries = _lexicon.load()
        self._entries = dict(entries)
        # Previews run under revisions the helper has never seen, so editing a
        # word and previewing it again is never answered from the cache.
        self._preview_rev = self._rev

        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: explains what the pronunciation list does.
        main.Add(wx.StaticText(self, label=_(
            "Words listed here are spoken using the phonemes you provide, "
            "instead of the pronunciation the voice would guess.")),
            border=5, flag=wx.ALL)
        # Translators: label for the list of pronunciation entries.
        main.Add(wx.StaticText(self, label=_("&Words:")), border=5,
                 flag=wx.LEFT | wx.TOP)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE, size=(520, 240))
        self._list.Bind(wx.EVT_LISTBOX, lambda e: self._update_buttons())
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: add a pronunciation entry.
        addBtn = wx.Button(self, label=_("&Add..."))
        addBtn.Bind(wx.EVT_BUTTON, self._on_add)
        # Translators: change the selected pronunciation entry.
        self._editBtn = wx.Button(self, label=_("&Edit..."))
        self._editBtn.Bind(wx.EVT_BUTTON, self._on_edit)
        # Translators: delete the selected pronunciation entry.
        self._removeBtn = wx.Button(self, label=_("&Remove"))
        self._removeBtn.Bind(wx.EVT_BUTTON, self._on_remove)
        # Translators: speak the selected word using its new pronunciation.
        self._previewBtn = wx.Button(self, label=_("&Preview"))
        self._previewBtn.Bind(wx.EVT_BUTTON, self._on_preview)
        for b in (addBtn, self._editBtn, self._removeBtn, self._previewBtn):
            btns.Add(b, border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        closeRow = wx.BoxSizer(wx.HORIZONTAL)
        okBtn = wx.Button(self, wx.ID_OK, label=_("&Save"))
        okBtn.Bind(wx.EVT_BUTTON, self._on_save)
        closeRow.Add(okBtn, border=4, flag=wx.ALL)
        closeRow.Add(wx.Button(self, wx.ID_CANCEL), border=4, flag=wx.ALL)
        main.Add(closeRow, flag=wx.ALIGN_CENTER)

        self.SetSizerAndFit(main)
        self._refresh()
        self._list.SetFocus()

    def _refresh(self, select_word=None):
        self._words = sorted(self._entries)
        # Translators: one pronunciation entry: {word} spoken as {ipa}.
        _set_list(self._list, [
            _("{word}: {ipa}").format(word=w, ipa=self._entries[w])
            for w in self._words])
        if self._words:
            index = 0
            if select_word in self._words:
                index = self._words.index(select_word)
            self._list.SetSelection(index)
        self._update_buttons()

    def _update_buttons(self):
        has = self._selected_word() is not None
        self._editBtn.Enable(has)
        self._removeBtn.Enable(has)
        self._previewBtn.Enable(has and self._preview_model is not None)

    def _selected_word(self):
        index = self._list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self._words):
            return None
        return self._words[index]

    def _on_add(self, evt):
        self._edit_entry("", "")

    def _on_edit(self, evt):
        word = self._selected_word()
        if word is not None:
            self._edit_entry(word, self._entries[word])

    def _edit_entry(self, word, ipa):
        dlg = PronunciationEntryDialog(self, word, ipa)
        if dlg.ShowModal() == wx.ID_OK:
            new_word, new_ipa = dlg.value()
            if new_word and new_ipa:
                if word and word != new_word:
                    self._entries.pop(word, None)
                self._entries[new_word] = new_ipa
                self._refresh(new_word)
        dlg.Destroy()

    def _on_remove(self, evt):
        word = self._selected_word()
        if word is None:
            return
        self._entries.pop(word, None)
        # Translators: {word} was deleted from the pronunciation list.
        _announce(_("Removed {word}").format(word=word))
        self._refresh()

    def _on_preview(self, evt):
        word = self._selected_word()
        if word is None or self._preview_model is None:
            return
        self._preview_rev += 1
        self._demo.speak_text(self._preview_model, word,
                              lexicon=(self._preview_rev, dict(self._entries)))

    def _on_save(self, evt):
        try:
            _lexicon.save(self._entries)
        except OSError as e:
            log.exception("piper: saving the lexicon failed")
            gui.messageBox(
                # Translators: {error} explains why saving failed.
                _("The pronunciations could not be saved: {error}")
                .format(error=e),
                _("Piper Neural Voices"), wx.OK | wx.ICON_ERROR, self)
            return
        self.EndModal(wx.ID_OK)


class PronunciationEntryDialog(wx.Dialog):
    """Add or change one word and its phonemes."""

    def __init__(self, parent, word, ipa):
        # Translators: title of the dialog for one pronunciation entry.
        super().__init__(parent, title=_("Pronunciation entry"))
        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: label for the word being given a pronunciation.
        main.Add(wx.StaticText(self, label=_("&Word:")), border=5, flag=wx.ALL)
        self._word = wx.TextCtrl(self, value=word, size=(320, -1))
        main.Add(self._word, border=5, flag=wx.ALL | wx.EXPAND)
        # Translators: label for the phonemes to speak instead.
        main.Add(wx.StaticText(self, label=_("&Pronunciation (IPA phonemes):")),
                 border=5, flag=wx.ALL)
        self._ipa = wx.TextCtrl(self, value=ipa, size=(320, -1))
        main.Add(self._ipa, border=5, flag=wx.ALL | wx.EXPAND)
        # Translators: example of the IPA phonemes expected in the field above.
        main.Add(wx.StaticText(self, label=_(
            "Example: NVDA spoken as en v ee d ee ay is "
            "\u025bnvi\u02d0di\u02d0\u02c8e\u026a")),
            border=5, flag=wx.ALL)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        btns.Add(wx.Button(self, wx.ID_OK), border=4, flag=wx.ALL)
        btns.Add(wx.Button(self, wx.ID_CANCEL), border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)
        self.SetSizerAndFit(main)
        self._word.SetFocus()

    def value(self):
        return self._word.GetValue().strip().lower(), self._ipa.GetValue().strip()


class LanguageVoicesDialog(wx.Dialog):
    """Choose which installed voice each language uses.

    NVDA switches language while reading multilingual documents. Without an
    assignment the first installed voice for a language wins, which is rarely
    the one a user with several voices per language wants.
    """

    def __init__(self, parent, installed):
        # Translators: title of the language assignment dialog.
        super().__init__(parent, title=_("Language voices"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._installed = installed
        self._by_key = {v.key: v for v in installed}
        self._mapping = _langvoices.load()
        self._languages = sorted({v.language for v in installed if v.language})

        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: explains what the language list does.
        main.Add(wx.StaticText(self, label=_(
            "When NVDA switches language, Piper uses the voice assigned "
            "here.")), border=5, flag=wx.ALL)
        # Translators: label for the list of languages.
        main.Add(wx.StaticText(self, label=_("&Languages:")), border=5,
                 flag=wx.LEFT | wx.TOP)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE, size=(520, 240))
        self._list.Bind(wx.EVT_LISTBOX, lambda e: None)
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: choose the voice for the selected language.
        changeBtn = wx.Button(self, label=_("&Change voice..."))
        changeBtn.Bind(wx.EVT_BUTTON, self._on_change)
        okBtn = wx.Button(self, wx.ID_OK, label=_("&Save"))
        okBtn.Bind(wx.EVT_BUTTON, self._on_save)
        btns.Add(changeBtn, border=4, flag=wx.ALL)
        btns.Add(okBtn, border=4, flag=wx.ALL)
        btns.Add(wx.Button(self, wx.ID_CANCEL), border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        self.SetSizerAndFit(main)
        self._refresh()
        self._list.SetFocus()

    def _voice_label(self, language):
        key = self._mapping.get(language)
        voice = self._by_key.get(key) if key else None
        if voice is None:
            # Translators: no explicit voice is assigned to this language.
            return _("automatic")
        return voice.display_name

    def _refresh(self, index=0):
        # Translators: one row of the language list: {language} uses {voice}.
        _set_list(self._list, [_("{language}: {voice}").format(
            language=lang, voice=self._voice_label(lang))
            for lang in self._languages])
        if self._languages:
            self._list.SetSelection(min(index, len(self._languages) - 1))

    def _on_change(self, evt):
        index = self._list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self._languages):
            return
        language = self._languages[index]
        # Translators: the option that restores automatic voice selection.
        choices = [_("Automatic")] + [v.display_name for v in self._installed]
        dlg = wx.SingleChoiceDialog(
            self,
            # Translators: {language} is a language code such as en_US.
            _("Voice for {language}").format(language=language),
            _("Language voices"), choices)
        current = self._mapping.get(language)
        if current in self._by_key:
            dlg.SetSelection(
                1 + [v.key for v in self._installed].index(current))
        if dlg.ShowModal() == wx.ID_OK:
            chosen = dlg.GetSelection()
            if chosen == 0:
                self._mapping.pop(language, None)
            else:
                self._mapping[language] = self._installed[chosen - 1].key
            self._refresh(index)
        dlg.Destroy()

    def _on_save(self, evt):
        try:
            _langvoices.save(self._mapping)
        except OSError as e:
            log.exception("piper: saving language voices failed")
            gui.messageBox(
                # Translators: {error} explains why saving failed.
                _("The language assignments could not be saved: {error}")
                .format(error=e),
                _("Piper Neural Voices"), wx.OK | wx.ICON_ERROR, self)
            return
        self.EndModal(wx.ID_OK)


def _cache_size_bytes():
    try:
        return os.path.getsize(_paths.cache_file())
    except OSError:
        return 0


class PreparedAudioDialog(wx.Dialog):
    """Manage the audio the helper prepares during idle time.

    The built-in list covers the alphabet and the words NVDA says constantly.
    What it cannot know is one person's own vocabulary: the app they live in,
    a colleague's name, a status message their tools repeat. Those go here.
    """

    def __init__(self, parent):
        # Translators: title of the prepared-audio dialog.
        super().__init__(parent, title=_("Prepared audio"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._words = _warmup.load()

        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: explains what preparing audio does.
        main.Add(wx.StaticText(self, label=_(
            "Piper always prepares the alphabet, the digits, punctuation "
            "and symbol names, and the words NVDA says most often while it "
            "is idle, so they speak with no delay; press Built-in items to "
            "see them. Add words and short phrases of your own to have "
            "them prepared too.")),
            border=5, flag=wx.ALL)
        # Translators: label for the list of phrases the user added.
        main.Add(wx.StaticText(self, label=_("Your &words and phrases:")),
                 border=5, flag=wx.LEFT | wx.TOP)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE, size=(520, 220))
        self._list.Bind(wx.EVT_LISTBOX, lambda e: self._update_buttons())
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: add a phrase to prepare.
        addBtn = wx.Button(self, label=_("&Add..."))
        addBtn.Bind(wx.EVT_BUTTON, self._on_add)
        # Translators: change the selected phrase.
        self._editBtn = wx.Button(self, label=_("&Edit..."))
        self._editBtn.Bind(wx.EVT_BUTTON, self._on_edit)
        # Translators: delete the selected phrase.
        self._removeBtn = wx.Button(self, label=_("&Remove"))
        self._removeBtn.Bind(wx.EVT_BUTTON, self._on_remove)
        # Translators: opens the read-only list of built-in prepared items.
        builtinBtn = wx.Button(self, label=_("Built-&in items..."))
        builtinBtn.Bind(wx.EVT_BUTTON, self._on_builtins)
        for b in (addBtn, self._editBtn, self._removeBtn, builtinBtn):
            btns.Add(b, border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        self._sizeLabel = wx.StaticText(self, label=self._size_text())
        main.Add(self._sizeLabel, border=5, flag=wx.ALL)
        rebuildRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: throw away the prepared audio and prepare it again.
        rebuildBtn = wx.Button(self, label=_("Re&build prepared audio"))
        rebuildBtn.Bind(wx.EVT_BUTTON, self._on_rebuild)
        rebuildRow.Add(rebuildBtn, border=4, flag=wx.ALL)
        main.Add(rebuildRow, flag=wx.ALIGN_CENTER)

        closeRow = wx.BoxSizer(wx.HORIZONTAL)
        okBtn = wx.Button(self, wx.ID_OK, label=_("&Save"))
        okBtn.Bind(wx.EVT_BUTTON, self._on_save)
        closeRow.Add(okBtn, border=4, flag=wx.ALL)
        closeRow.Add(wx.Button(self, wx.ID_CANCEL), border=4, flag=wx.ALL)
        main.Add(closeRow, flag=wx.ALIGN_CENTER)

        self.SetSizerAndFit(main)
        self._refresh()
        self._list.SetFocus()

    def _size_text(self):
        megabytes = _cache_size_bytes() / _MB
        # Translators: {size} is the size of the prepared audio in megabytes.
        return _("Prepared audio currently uses {size} MB.").format(
            size="%.1f" % megabytes)

    def _refresh(self, select=None):
        _set_list(self._list, self._words)
        if self._words:
            index = self._words.index(select) if select in self._words else 0
            self._list.SetSelection(index)
        self._update_buttons()

    def _update_buttons(self):
        has = self._selected() is not None
        self._editBtn.Enable(has)
        self._removeBtn.Enable(has)

    def _selected(self):
        index = self._list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self._words):
            return None
        return self._words[index]

    def _ask(self, title, value):
        dlg = wx.TextEntryDialog(
            self,
            # Translators: {limit} is the longest phrase that can be prepared.
            _("Word or phrase, up to {limit} characters:").format(
                limit=_warmup.MAX_LENGTH),
            title, value)
        text = dlg.GetValue() if dlg.ShowModal() == wx.ID_OK else None
        dlg.Destroy()
        return text

    def _on_add(self, evt):
        # Translators: title of the prompt for a new phrase.
        text = self._ask(_("Add a phrase"), "")
        self._store(None, text)

    def _on_edit(self, evt):
        current = self._selected()
        if current is None:
            return
        # Translators: title of the prompt for changing a phrase.
        self._store(current, self._ask(_("Edit the phrase"), current))

    def _store(self, previous, text):
        if text is None:
            return
        # The same normalization clean() applies, so the checks below judge
        # what would actually be stored rather than the raw keystrokes.
        word = " ".join(text.split())
        if not word:
            return
        if len(word) > _warmup.MAX_LENGTH:
            gui.messageBox(
                # Translators: {limit} is the longest phrase allowed.
                _("A phrase must be no longer than {limit} characters. "
                  "Longer text is split before it is spoken, so preparing it "
                  "would not make anything faster.").format(
                      limit=_warmup.MAX_LENGTH),
                _("Piper Neural Voices"), wx.OK | wx.ICON_INFORMATION, self)
            return
        others = [w for w in self._words if w != previous]
        duplicate = next(
            (w for w in others if w.lower() == word.lower()), None)
        if duplicate is not None:
            # Translators: the phrase is already listed as {word}.
            _announce(_("Already in the list as {word}").format(
                word=duplicate))
            self._refresh(duplicate)
            return
        candidate = list(self._words)
        if previous is not None and previous in candidate:
            candidate[candidate.index(previous)] = word
        else:
            candidate.append(word)
        self._words = _warmup.clean(candidate)
        self._refresh(word)

    def _on_remove(self, evt):
        current = self._selected()
        if current is None:
            return
        self._words = [w for w in self._words if w != current]
        # Translators: {word} was removed from the prepared list.
        _announce(_("Removed {word}").format(word=current))
        self._refresh()

    def _on_builtins(self, evt):
        dlg = BuiltinPreparedDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_rebuild(self, evt):
        """Throw the prepared audio away and start again.

        The running synthesizer owns the file, so it has to do the work; when
        Piper is not the active synthesizer there is nothing holding it and
        the file can simply go.
        """
        if not _notify_synth("rebuild_cache"):
            try:
                os.remove(_paths.cache_file())
            except OSError:
                pass
        self._sizeLabel.SetLabel(self._size_text())
        _announce(_("Rebuilding prepared audio"))

    def _on_save(self, evt):
        try:
            _warmup.save(self._words)
        except OSError as e:
            log.exception("piper: saving the prepared phrases failed")
            gui.messageBox(
                # Translators: {error} explains why saving failed.
                _("The phrases could not be saved: {error}").format(error=e),
                _("Piper Neural Voices"), wx.OK | wx.ICON_ERROR, self)
            return
        self.EndModal(wx.ID_OK)


class BuiltinPreparedDialog(wx.Dialog):
    """Read-only view of what the helper prepares without being asked.

    The editable list next door holds only the user's own phrases; showing
    the few hundred built-ins there would bury them and imply they can be
    edited. Here they can be arrowed through and heard, which answers "is
    this one already covered?" before adding it by hand.
    """

    def __init__(self, parent):
        # Translators: title of the read-only list of built-in prepared items.
        super().__init__(parent, title=_("Built-in prepared items"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        items = _warmup.builtin_items()
        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: explains the read-only list of built-in items.
        main.Add(wx.StaticText(self, label=_(
            "Piper prepares these for every voice on its own, in this "
            "order, after anything you added yourself. The symbol names "
            "come from NVDA in your language. This list is read only.")),
            border=5, flag=wx.ALL)
        # Translators: label for the read-only list; {count} is how many.
        main.Add(wx.StaticText(self, label=_(
            "Prepared &items ({count}):").format(count=len(items))),
            border=5, flag=wx.LEFT | wx.TOP)
        self._list = wx.ListBox(self, style=wx.LB_SINGLE, size=(520, 300))
        _set_list(self._list, items)
        if items:
            self._list.SetSelection(0)
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)
        closeRow = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: closes the read-only list.
        closeRow.Add(wx.Button(self, wx.ID_CANCEL, label=_("&Close")),
                     border=4, flag=wx.ALL)
        main.Add(closeRow, flag=wx.ALIGN_CENTER)
        self.SetSizerAndFit(main)
        self._list.SetFocus()


class DownloadSeveralDialog(wx.Dialog):
    """Download a batch of voices in one go.

    Setting up several languages a voice at a time is tedious, and the main
    list stays a plain list so that browsing it does not have to announce a
    checkbox state on every item.
    """

    def __init__(self, parent, voices):
        # Translators: title of the batch download dialog.
        super().__init__(parent, title=_("Download several voices"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._voices = [v for v in voices if not v.installed]
        main = wx.BoxSizer(wx.VERTICAL)
        if not self._voices:
            # Translators: shown when the filtered list is all installed.
            main.Add(wx.StaticText(self, label=_(
                "Every voice matching your filters is already installed.")),
                border=5, flag=wx.ALL)
        else:
            # Translators: label for the list of voices to download.
            main.Add(wx.StaticText(self, label=_("&Voices to download:")),
                     border=5, flag=wx.ALL)
        labels = [
            # Translators: {name} is a voice and {size} its size in megabytes.
            _("{name} - {size} MB").format(
                name=v.display_name, size=round((v.model_size or 0) / _MB))
            for v in self._voices
        ]
        self._list = _CheckListBox(self, choices=labels, size=(520, 260))
        main.Add(self._list, proportion=1, border=5, flag=wx.ALL | wx.EXPAND)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: starts downloading the checked voices.
        downloadBtn = wx.Button(self, wx.ID_OK, label=_("&Download"))
        downloadBtn.Bind(wx.EVT_BUTTON, self._on_download)
        downloadBtn.Enable(bool(self._voices))
        btns.Add(downloadBtn, border=4, flag=wx.ALL)
        btns.Add(wx.Button(self, wx.ID_CANCEL), border=4, flag=wx.ALL)
        main.Add(btns, flag=wx.ALIGN_CENTER)

        self.SetSizerAndFit(main)
        self._list.SetFocus()

    def _on_download(self, evt):
        chosen = [self._voices[i] for i in self._list.GetCheckedItems()]
        if not chosen:
            self.EndModal(wx.ID_CANCEL)
            return
        done = 0
        for voice in chosen:
            if not _download_voice_with_progress(self, voice):
                break
            done += 1
        if done:
            _notify_synth("reload_installed_voices")
        # Translators: {done} of {total} voices were downloaded.
        _announce(_("Downloaded {done} of {total} voices").format(
            done=done, total=len(chosen)))
        self.EndModal(wx.ID_OK)


class SettingsFilesDialog(wx.Dialog):
    """Back up, restore, or reset the settings a user has built up.

    Voices download again and prepared audio rebuilds itself. Corrected
    pronunciations, per-language voices, prepared phrases and per-voice
    settings are the part that would have to be done again by hand.
    """

    def __init__(self, parent):
        # Translators: title of the backup and restore dialog.
        super().__init__(parent, title=_("Back up or restore settings"))
        main = wx.BoxSizer(wx.VERTICAL)
        # Translators: explains what is included in a backup.
        main.Add(wx.StaticText(self, label=_(
            "A backup holds your pronunciations, the voice you chose for each "
            "language, the phrases you asked to have prepared, and your "
            "per-voice settings. Voices themselves are not included; they can "
            "be downloaded again.")), border=5, flag=wx.ALL)

        btns = wx.BoxSizer(wx.VERTICAL)
        # Translators: writes a settings backup file.
        backupBtn = wx.Button(self, label=_("&Back up settings..."))
        backupBtn.Bind(wx.EVT_BUTTON, self._on_backup)
        # Translators: reads a settings backup file back in.
        restoreBtn = wx.Button(self, label=_("&Restore settings..."))
        restoreBtn.Bind(wx.EVT_BUTTON, self._on_restore)
        # Translators: throws away all of the add-on's settings.
        resetBtn = wx.Button(self, label=_("Reset all settings..."))
        resetBtn.Bind(wx.EVT_BUTTON, self._on_reset)
        for b in (backupBtn, restoreBtn, resetBtn):
            btns.Add(b, border=4, flag=wx.ALL | wx.EXPAND)
        main.Add(btns, border=5, flag=wx.ALL | wx.EXPAND)
        main.Add(wx.Button(self, wx.ID_CANCEL, label=_("&Close")),
                 border=5, flag=wx.ALL | wx.ALIGN_CENTER)
        self.SetSizerAndFit(main)
        backupBtn.SetFocus()

    def _on_backup(self, evt):
        dlg = wx.FileDialog(
            self,
            # Translators: title of the save dialog for a settings backup.
            message=_("Save your Piper settings"),
            defaultFile="piper-settings.zip",
            # Translators: the file type of a settings backup.
            wildcard=_("Piper settings backup (*.zip)|*.zip"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        try:
            written = _backup.backup(path)
        except _backup.BackupError as e:
            self._failed(_("The backup could not be written: {error}"), e)
            return
        # Translators: {count} settings files were saved.
        _announce(_("Backed up {count} settings files").format(
            count=len(written)))

    def _on_restore(self, evt):
        dlg = wx.FileDialog(
            self,
            # Translators: title of the open dialog for a settings backup.
            message=_("Choose a Piper settings backup"),
            # Translators: the file type of a settings backup.
            wildcard=_("Piper settings backup (*.zip)|*.zip"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        try:
            restored = _backup.restore(path)
        except _backup.BackupError as e:
            self._failed(_("That backup could not be restored: {error}"), e)
            return
        self._reload()
        # Translators: {count} settings files were read back in.
        _announce(_("Restored {count} settings files").format(
            count=len(restored)))

    def _on_reset(self, evt):
        result = gui.messageBox(
            # Translators: asked before throwing settings away.
            _("This deletes your pronunciations, language voices, prepared "
              "phrases and per-voice settings. Your downloaded voices are "
              "kept. Continue?"),
            _("Piper Neural Voices"), wx.YES_NO | wx.ICON_WARNING, self)
        if result != wx.YES:
            return
        removed = _backup.reset()
        self._reload()
        # Translators: {count} settings files were deleted.
        _announce(_("Reset {count} settings files").format(count=len(removed)))

    def _reload(self):
        for method in ("reload_lexicon", "reload_language_voices",
                       "reload_warmup_words", "reload_voice_settings"):
            _notify_synth(method)

    def _failed(self, template, error):
        log.exception("piper: settings backup operation failed")
        gui.messageBox(template.format(error=error), _("Piper Neural Voices"),
                       wx.OK | wx.ICON_ERROR, self)
