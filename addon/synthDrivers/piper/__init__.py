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
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting
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

from . import _audio, _download, _helperProc, _paths, _protocol as proto, _voices

SAMPLE_RATE = 22050

_PITCH_SEMITONE_RANGE = 4.0
_STRETCH_AT_MIN_RATE = 0.6
_STRETCH_AT_MID_RATE = 1.0
_STRETCH_AT_MAX_RATE = 2.0
_RATE_BOOST_MAX_EXTRA = 0.5


class SynthDriver(SynthDriverBase):
    name = "piper"
    description = "Piper Neural Voices"

    supportedSettings = (
        SynthDriverBase.VoiceSetting(),
        SynthDriverBase.VariantSetting(),  # speaker, for multi-speaker voices
        SynthDriverBase.RateSetting(),
        SynthDriverBase.RateBoostSetting(),
        SynthDriverBase.PitchSetting(),
        SynthDriverBase.VolumeSetting(),
        BooleanDriverSetting(
            "useGpu",
            # Translators: optional GPU acceleration toggle.
            _("Use &GPU acceleration (DirectML) if available"),
            defaultVal=False,
        ),
    )

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
        self._useGpu = self._load_conf("useGpu", False)

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
        self._request_warmup()

    def _helper_args(self):
        args = [
            "--espeak-dll", _paths.ESPEAK_DLL,
            "--espeak-data", _paths.ESPEAK_DATA,
            "--cache-dir", _paths.cache_dir(),
        ]
        if self._useGpu:
            args.append("--dml")
        return args

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
                self._helper.send(proto.LOAD_VOICE, {"voice": model})
            except Exception:
                pass

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

    def _get_useGpu(self):
        return self._useGpu

    def _set_useGpu(self, value):
        value = bool(value)
        if value != self._useGpu:
            self._useGpu = value
            self._save_conf("useGpu", value)
            self._restart_helper()

    def _restart_helper(self):
        try:
            self._helper.terminate()
        except Exception:
            pass
        self._helper = _helperProc.HelperProcess(
            _paths.HELPER_EXE, self._helper_args(),
            on_frame=self._on_frame, on_restart=self._on_helper_restart)
        self._helper.start()
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
