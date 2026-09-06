"""NVDA speech synthesizer driver for Piper neural voices.

Inference runs in a bundled x64 helper process (see the helper/ crate). Each
Piper voice is a separate ONNX model; segments tell the helper which model
file and speaker to use. Audio streams through nvwave.WavePlayer with
playback-accurate index/done notifications.
"""

import os
import threading
from collections import OrderedDict

import config
import nvwave
import synthDriverHandler
from autoSettingsUtils.driverSetting import (
    BooleanDriverSetting,
    NumericDriverSetting,
)
from autoSettingsUtils.utils import StringParameterInfo
from logHandler import log
from synthDriverHandler import (
    SynthDriver as SynthDriverBase,
    VoiceInfo,
    synthDoneSpeaking,
    synthIndexReached,
)

from speech.commands import (
    BreakCommand,
    CharacterModeCommand,
    IndexCommand,
    LangChangeCommand,
    PitchCommand,
    RateCommand,
    VolumeCommand,
)

from . import (
    _audio,
    _helperProc,
    _langvoices,
    _lexicon,
    _paths,
    _protocol as proto,
    _voices,
)

SAMPLE_RATE = 22050

_PITCH_SEMITONE_RANGE = 4.0
# Expressiveness maps 0-100 onto a multiplier for the voice's trained noise
# scales: 50 keeps the voice exactly as trained, lower is flatter and steadier
# (easier to follow at speed), higher is more varied.
_VARIANCE_AT_MIN = 0.4
_VARIANCE_AT_MID = 1.0
_VARIANCE_AT_MAX = 1.6
# Advanced mode exposes Piper's own inference parameters instead, as
# percentages of whatever the voice was trained with: 50 is the trained value
# and 100 is twice it. Working in percentages rather than absolute numbers
# keeps one setting meaningful across voices that were trained differently.
_ADVANCED_MID = 50.0
_STRETCH_AT_MIN_RATE = 0.6
_STRETCH_AT_MID_RATE = 1.0
_STRETCH_AT_MAX_RATE = 2.0
_RATE_BOOST_MAX_EXTRA = 0.5


class SynthDriver(SynthDriverBase):
    name = "piper"
    description = "Piper Neural Voices"

    @classmethod
    def _base_settings(cls):
        return (
            SynthDriverBase.VoiceSetting(),
            SynthDriverBase.VariantSetting(),  # speaker, multi-speaker voices
            SynthDriverBase.RateSetting(),
            SynthDriverBase.RateBoostSetting(),
            SynthDriverBase.PitchSetting(),
            SynthDriverBase.VolumeSetting(),
            BooleanDriverSetting(
                "advancedMode",
                # Translators: reveals the voice's raw inference parameters.
                _("Show &advanced voice parameters"),
                defaultVal=False,
            ),
        )

    @classmethod
    def _simple_settings(cls):
        return (
            NumericDriverSetting(
                "variance",
                # Translators: how much the voice varies its delivery.
                _("&Expressiveness"),
                availableInSettingsRing=True,
                defaultVal=50,
                minStep=5,
            ),
        )

    @classmethod
    def _advanced_settings(cls):
        """Piper's own inference parameters, named as Piper names them so
        that people coming from other Piper tools recognize them. Each is a
        percentage of the voice's trained value, where 50 is that value."""
        return (
            NumericDriverSetting(
                "noiseScale",
                # Translators: Piper's noise_scale parameter.
                _("&Noise scale (variability)"),
                availableInSettingsRing=True,
                defaultVal=50,
                minStep=5,
            ),
            NumericDriverSetting(
                "noiseW",
                # Translators: Piper's noise_w parameter.
                _("Noise &W (phoneme length variation)"),
                availableInSettingsRing=True,
                defaultVal=50,
                minStep=5,
            ),
            NumericDriverSetting(
                "lengthScale",
                # Translators: Piper's length_scale parameter.
                _("&Length scale (model pace)"),
                availableInSettingsRing=True,
                defaultVal=50,
                minStep=5,
            ),
        )

    def _get_supportedSettings(self):
        """Which settings NVDA shows. Computed rather than fixed so advanced
        mode can reveal the raw parameters, and so the simple Expressiveness
        control disappears when it would fight with them."""
        if getattr(self, "_advancedMode", False):
            return self._base_settings() + self._advanced_settings()
        return self._base_settings() + self._simple_settings()

    supportedCommands = frozenset({
        IndexCommand,
        CharacterModeCommand,
        LangChangeCommand,
        BreakCommand,
        PitchCommand,
        RateCommand,
        VolumeCommand,
    })
    supportedNotifications = frozenset({synthIndexReached, synthDoneSpeaking})

    @classmethod
    def check(cls):
        return os.path.isfile(_paths.HELPER_EXE)

    def __init__(self):
        super().__init__()
        self._rate = 50
        self._pitch = 50
        self._volume = 90
        self._rateBoost = False
        self._variant = "0"
        self._variance = _clamp_percent(self._load_conf("variance", 50))
        self._advancedMode = bool(self._load_conf("advancedMode", False))
        self._noiseScale = _clamp_percent(self._load_conf("noiseScale", 50))
        self._noiseW = _clamp_percent(self._load_conf("noiseW", 50))
        self._lengthScale = _clamp_percent(self._load_conf("lengthScale", 50))
        self._lang_voices = _langvoices.load()

        self._voices = _voices.load_installed()
        self._voice_by_key = {v.key: v for v in self._voices}
        self._voice = self._voices[0].key if self._voices else ""
        self._utterance_counter = 0
        self._lock = threading.Lock()

        if not self._voices:
            # No voices installed yet: prompt to open the voice manager.
            if not self._prompt_install():
                raise RuntimeError("No Piper voices installed")
            self._voices = _voices.load_installed()
            self._voice_by_key = {v.key: v for v in self._voices}
            if self._voices:
                self._voice = self._voices[0].key
            else:
                raise RuntimeError("No Piper voices installed")

        self._player = _create_player()
        self._pump = _audio.AudioPump(self._player, self._on_index, self._on_done)
        self._helper = _helperProc.HelperProcess(
            _paths.HELPER_EXE, self._helper_args(),
            on_frame=self._on_frame, on_restart=self._on_helper_restart)
        self._helper.start()
        self._send_lexicon()
        self._request_warmup()

    def _helper_args(self):
        return [
            "--espeak-dll", _paths.ESPEAK_DLL,
            "--espeak-data", _paths.ESPEAK_DATA,
            "--cache-dir", _paths.cache_dir(),
        ]

    def _prompt_install(self):
        try:
            from . import _manager_ui
        except Exception:
            log.exception("piper: manager UI unavailable")
            return False
        return _manager_ui.prompt_first_run()

    def _request_warmup(self):
        model = _paths.voice_model_path(self._voice)
        if os.path.isfile(model):
            try:
                self._helper.send(proto.LOAD_VOICE, {
                    "voice": model,
                    "scales": self._scales(),
                })
            except Exception:
                pass

    def _send_lexicon(self):
        """Push the user's pronunciation overrides to the helper."""
        try:
            rev, entries = _lexicon.load()
            self._helper.send(proto.SET_LEXICON, _lexicon.message(rev, entries))
        except Exception:
            log.exception("piper: could not send the pronunciation lexicon")

    def reload_lexicon(self):
        """Called by the voice manager after the user edits pronunciations."""
        self._send_lexicon()

    def reload_language_voices(self):
        """Called by the voice manager after language assignments change."""
        self._lang_voices = _langvoices.load()

    def terminate(self):
        try:
            self._helper.terminate()
        except Exception:
            pass
        try:
            self._pump.shutdown()
        except Exception:
            pass
        try:
            self._player.close()
        except Exception:
            pass
        super().terminate()

    # -- frame dispatch ----------------------------------------------------

    def _on_frame(self, msg_type, payload):
        if msg_type in (proto.AUDIO, proto.MARKER, proto.DONE):
            self._pump.handle_frame(msg_type, payload)
        elif msg_type == proto.ERROR:
            info = proto.parse_json(payload)
            log.warning("piper helper error %s: %s"
                        % (info.get("code"), info.get("message")))
        elif msg_type == proto.LOG:
            info = proto.parse_json(payload)
            level = info.get("level", "info")
            getattr(log, level if hasattr(log, level) else "info")(
                "piper helper: %s" % info.get("message"))

    def _on_helper_restart(self):
        self._send_lexicon()
        self._request_warmup()

    def _on_index(self, index):
        synthIndexReached.notify(synth=self, index=index)

    def _on_done(self):
        synthDoneSpeaking.notify(synth=self)

    # -- speech ------------------------------------------------------------

    def speak(self, speechSequence):
        job = self._build_job(speechSequence)
        try:
            self._helper.send(proto.SPEAK, job)
        except Exception:
            log.exception("piper: failed to send speak job")

    def _build_job(self, speechSequence):
        with self._lock:
            self._utterance_counter += 1
            uid = self._utterance_counter

        base = self._voice_by_key.get(self._voice)
        base_model = _paths.voice_model_path(self._voice) if base else ""
        base_sid = self._current_sid(base)
        auto_lang = config.conf["speech"].get("autoLanguageSwitching", True)

        cur_model = base_model
        cur_sid = base_sid
        char_mode = False
        pitch = self._pitch
        rate = self._rate
        volume = self._volume

        segments = []
        pending_indexes = []
        pending_break = 0
        cur = None

        def new_segment():
            _speed, stretch = self._rate_to_stretch(rate)
            return {
                "text": "",
                "modelPath": cur_model,
                "sid": cur_sid,
                "stretch": stretch,
                "pitchSemis": self._pitch_to_semitones(pitch),
                "volume": max(0.0, min(1.0, volume / 100.0)),
                "breakMsBefore": 0,
                "indexesBefore": [],
                "charMode": char_mode,
                "scales": self._scales(),
            }

        def open_segment():
            nonlocal cur, pending_indexes, pending_break
            cur = new_segment()
            cur["indexesBefore"] = pending_indexes
            cur["breakMsBefore"] = pending_break
            pending_indexes = []
            pending_break = 0

        def close_segment():
            nonlocal cur
            if cur is not None and (cur["text"].strip() or cur["breakMsBefore"]
                                    or cur["indexesBefore"]):
                segments.append(cur)
            cur = None

        for item in speechSequence:
            if isinstance(item, str):
                if cur is None:
                    open_segment()
                cur["text"] += item
            elif isinstance(item, IndexCommand):
                close_segment()
                pending_indexes.append(item.index)
            elif isinstance(item, CharacterModeCommand):
                close_segment()
                char_mode = item.state
            elif isinstance(item, LangChangeCommand):
                close_segment()
                if item.lang and auto_lang:
                    cur_model, cur_sid = self._model_for_lang(
                        item.lang, base_model, base_sid)
                else:
                    cur_model, cur_sid = base_model, base_sid
            elif isinstance(item, BreakCommand):
                close_segment()
                pending_break += int(item.time)
            elif isinstance(item, PitchCommand):
                close_segment()
                pitch = _clamp_percent(item.newValue)
            elif isinstance(item, RateCommand):
                close_segment()
                rate = _clamp_percent(item.newValue)
            elif isinstance(item, VolumeCommand):
                close_segment()
                volume = _clamp_percent(item.newValue)
        close_segment()

        if pending_indexes or pending_break:
            open_segment()
            close_segment()

        return {"utteranceId": uid, "segments": segments, "indexesAfter": []}

    def cancel(self):
        self._pump.cancel()
        try:
            self._helper.send(proto.CANCEL, {})
        except Exception:
            pass

    def pause(self, switch):
        self._pump.pause(switch)

    # -- parameter mapping -------------------------------------------------

    def _rate_to_stretch(self, rate):
        rate = _clamp_percent(rate)
        if rate <= 50:
            stretch = _STRETCH_AT_MIN_RATE + (rate / 50.0) * (
                _STRETCH_AT_MID_RATE - _STRETCH_AT_MIN_RATE)
        else:
            stretch = _STRETCH_AT_MID_RATE + ((rate - 50) / 50.0) * (
                _STRETCH_AT_MAX_RATE - _STRETCH_AT_MID_RATE)
        if self._rateBoost:
            stretch *= 1.0 + (rate / 100.0) * _RATE_BOOST_MAX_EXTRA
        return 1.0, round(stretch, 3)

    def _variance_factor(self):
        """Expressiveness percentage as a multiplier for the model's noise
        scales. Part of the helper's cache key, so it is rounded to keep the
        cache from fragmenting on tiny differences."""
        value = _clamp_percent(self._variance)
        if value <= 50:
            factor = _VARIANCE_AT_MIN + (value / 50.0) * (
                _VARIANCE_AT_MID - _VARIANCE_AT_MIN)
        else:
            factor = _VARIANCE_AT_MID + ((value - 50) / 50.0) * (
                _VARIANCE_AT_MAX - _VARIANCE_AT_MID)
        return round(factor, 2)

    def _scales(self):
        """The inference-parameter multipliers for the helper.

        In simple mode one Expressiveness control drives both noise
        parameters and the model's pace is left alone. In advanced mode each
        parameter is set directly, as a percentage of the voice's trained
        value.
        """
        if self._advancedMode:
            return {
                "noiseScale": _advanced_factor(self._noiseScale),
                "noiseW": _advanced_factor(self._noiseW),
                "lengthScale": _advanced_factor(self._lengthScale),
            }
        variance = self._variance_factor()
        return {
            "noiseScale": variance,
            "noiseW": variance,
            "lengthScale": 1.0,
        }

    def _pitch_to_semitones(self, pitch):
        pitch = _clamp_percent(pitch)
        return round((pitch - 50) / 50.0 * _PITCH_SEMITONE_RANGE, 3)

    def _current_sid(self, voice):
        if voice is None or voice.num_speakers <= 1:
            return 0
        try:
            return int(self._variant)
        except (TypeError, ValueError):
            return 0

    def _model_for_lang(self, lang, base_model, base_sid):
        # An explicit assignment from the voice manager wins; otherwise fall
        # back to the first installed voice for that language.
        key = _langvoices.resolve(self._lang_voices, lang, self._voice_by_key)
        if key is None:
            key = _voices.default_voice_for_language(
                self._voices, lang.replace("-", "_"))
        if key and key in self._voice_by_key:
            return _paths.voice_model_path(key), 0
        return base_model, base_sid

    # -- settings ----------------------------------------------------------

    def _get_rate(self):
        return self._rate

    def _set_rate(self, v):
        self._rate = _clamp_percent(v)

    def _get_rateBoost(self):
        return self._rateBoost

    def _set_rateBoost(self, v):
        self._rateBoost = bool(v)

    def _get_pitch(self):
        return self._pitch

    def _set_pitch(self, v):
        self._pitch = _clamp_percent(v)

    def _get_volume(self):
        return self._volume

    def _set_volume(self, v):
        self._volume = _clamp_percent(v)

    def _get_voice(self):
        return self._voice

    def _set_voice(self, value):
        if value in self._voice_by_key and value != self._voice:
            self._voice = value
            self._variant = "0"
            self._request_warmup()

    def _getAvailableVoices(self):
        result = OrderedDict()
        for v in self._voices:
            result[v.key] = VoiceInfo(v.key, v.display_name, v.language)
        return result

    def _get_variant(self):
        return self._variant

    def _set_variant(self, value):
        self._variant = value

    def _getAvailableVariants(self):
        result = OrderedDict()
        voice = self._voice_by_key.get(self._voice)
        if voice is None or voice.num_speakers <= 1:
            # Translators: shown when a voice has a single speaker.
            result["0"] = StringParameterInfo("0", _("Default"))
            return result
        # Map speaker labels to their sid; show label as the display name.
        by_sid = {}
        for label, sid in voice.speaker_id_map.items():
            by_sid[int(sid)] = label
        for sid in range(voice.num_speakers):
            label = by_sid.get(sid, str(sid))
            result[str(sid)] = StringParameterInfo(
                str(sid),
                # Translators: {label} is a speaker name/number.
                _("Speaker {label}").format(label=label))
        return result

    def _get_variance(self):
        return self._variance

    def _set_variance(self, value):
        self._set_scale_setting("variance", value)

    def _get_noiseScale(self):
        return self._noiseScale

    def _set_noiseScale(self, value):
        self._set_scale_setting("noiseScale", value)

    def _get_noiseW(self):
        return self._noiseW

    def _set_noiseW(self, value):
        self._set_scale_setting("noiseW", value)

    def _get_lengthScale(self):
        return self._lengthScale

    def _set_lengthScale(self, value):
        self._set_scale_setting("lengthScale", value)

    def _set_scale_setting(self, name, value):
        """Store one inference-parameter percentage and re-warm.

        Cached audio is keyed by these values, so changing one leaves echo
        uncached until the common words are prepared again.
        """
        value = _clamp_percent(value)
        attr = "_" + name
        if value == getattr(self, attr):
            return
        setattr(self, attr, value)
        self._save_conf(name, value)
        self._request_warmup()

    def _get_advancedMode(self):
        return self._advancedMode

    def _set_advancedMode(self, value):
        value = bool(value)
        if value == self._advancedMode:
            return
        self._advancedMode = value
        self._save_conf("advancedMode", value)
        # Which settings exist has changed, so the open settings panel is now
        # showing the wrong set.
        if not _refresh_settings_panel():
            _announce_settings_change()
        self._request_warmup()

    def _load_conf(self, key, default):
        try:
            return config.conf["speech"][self.name].get(key, default)
        except Exception:
            return default

    def _save_conf(self, key, value):
        try:
            config.conf["speech"][self.name][key] = value
        except Exception:
            pass


def _advanced_factor(percent):
    """An advanced percentage as a multiplier of the voice's trained value:
    50 means "as trained", 100 means twice it. Rounded because the value is
    part of the helper's cache key."""
    return round(_clamp_percent(percent) / _ADVANCED_MID, 2)


def _refresh_settings_panel():
    """Rebuild the open Speech settings panel, if there is one.

    Toggling advanced mode adds or removes settings, and NVDA builds those
    controls when the panel opens. Refreshing in place is best effort: it
    depends on NVDA internals, so failure is not an error, only a reason to
    tell the user to reopen the dialog.
    """
    try:
        import wx
        from gui.settingsDialogs import NVDASettingsDialog
    except Exception:
        return False
    try:
        for window in wx.GetTopLevelWindows():
            if not isinstance(window, NVDASettingsDialog):
                continue
            panel = getattr(window, "currentCategory", None)
            for candidate in (getattr(panel, "voicePanel", None), panel):
                update = getattr(candidate, "updateDriverSettings", None)
                if update is not None:
                    update()
                    return True
    except Exception:
        log.debug("piper: could not refresh the settings panel", exc_info=True)
    return False


def _announce_settings_change():
    try:
        import ui
        ui.message(
            # Translators: spoken after turning advanced parameters on or off.
            _("Reopen Speech settings to see the changed parameters"))
    except Exception:
        pass


def _clamp_percent(value):
    try:
        value = int(round(value))
    except (TypeError, ValueError):
        return 50
    return max(0, min(100, value))


def _create_player():
    kwargs = dict(channels=1, samplesPerSec=SAMPLE_RATE, bitsPerSample=16,
                  wantDucking=True)
    try:
        return nvwave.WavePlayer(purpose=nvwave.AudioPurpose.SPEECH, **kwargs)
    except (AttributeError, TypeError):
        pass
    try:
        outputDevice = config.conf["speech"]["outputDevice"]
        return nvwave.WavePlayer(outputDevice=outputDevice, **kwargs)
    except TypeError:
        return nvwave.WavePlayer(**kwargs)
