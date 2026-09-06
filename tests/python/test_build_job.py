"""Tests for Piper speech-sequence -> SPEAK job conversion."""

import threading

import pytest

import synthDrivers.piper as piper
from synthDrivers.piper import _paths, _protocol as proto, _voices
from speech.commands import (
    BreakCommand, CharacterModeCommand, IndexCommand, LangChangeCommand,
    PhonemeCommand, PitchCommand, RateCommand,
)


def _voice(key, lang, num_speakers=1, speaker_map=None):
    return _voices.InstalledVoice(
        key=key, display_name=key, language=lang, espeak_lang="en-us",
        num_speakers=num_speakers, speaker_id_map=speaker_map or {})


@pytest.fixture
def driver(tmp_path, monkeypatch):
    # Keep anything the driver writes out of the source tree.
    monkeypatch.setenv("PIPER_DATA_DIR", str(tmp_path / "config"))
    d = piper.SynthDriver.__new__(piper.SynthDriver)
    vs = [
        _voice("en_US-lessac-medium", "en_US"),
        _voice("fr_FR-siwis-medium", "fr_FR"),
        _voice("en_US-libritts-high", "en_US", num_speakers=3,
               speaker_map={"a": 0, "b": 1, "c": 2}),
    ]
    d._voices = vs
    d._voice_by_key = {v.key: v for v in vs}
    d._voice = "en_US-lessac-medium"
    d._rate = 50
    d._pitch = 50
    d._volume = 90
    d._rateBoost = False
    d._variant = "0"
    d._variance = 50
    d._sentencePause = 25
    d._advancedMode = False
    d._noiseScale = 50
    d._noiseW = 50
    d._lengthScale = 50
    d._lang_voices = {}
    d._rememberPerVoice = True
    d._voice_settings = {}
    d._favorites = []
    d._lock = threading.Lock()
    d._utterance_counter = 0
    return d


def test_simple_text(driver):
    job = driver._build_job(["Hello world"])
    assert len(job["segments"]) == 1
    seg = job["segments"][0]
    assert seg["text"] == "Hello world"
    assert seg["modelPath"] == _paths.voice_model_path("en_US-lessac-medium")
    assert seg["sid"] == 0


def test_index_boundary(driver):
    job = driver._build_job(["Hello", IndexCommand(5), "world"])
    segs = job["segments"]
    assert len(segs) == 2
    assert segs[1]["indexesBefore"] == [5]


def test_language_switch_changes_model(driver):
    job = driver._build_job(["hi ", LangChangeCommand("fr"), "bonjour"])
    segs = job["segments"]
    assert "lessac" in segs[0]["modelPath"]
    assert "siwis" in segs[1]["modelPath"]


def test_break_and_charmode(driver):
    job = driver._build_job(
        [CharacterModeCommand(True), "b", CharacterModeCommand(False),
         BreakCommand(200), "next"])
    segs = job["segments"]
    assert segs[0]["charMode"] is True
    assert any(s["breakMsBefore"] == 200 for s in segs)


def test_pitch_command(driver):
    base = driver._build_job(["a"])["segments"][0]["pitchSemis"]
    high = driver._build_job(
        ["a", PitchCommand(newValue=100), "B"])["segments"][1]["pitchSemis"]
    assert high > base


def test_rate_is_stretch_only(driver):
    # Model speed is always 1.0; rate lives entirely in stretch.
    speed, slow = driver._rate_to_stretch(0)
    assert speed == 1.0
    _s, fast = driver._rate_to_stretch(100)
    assert fast > slow
    driver._rateBoost = True
    _s2, boosted = driver._rate_to_stretch(100)
    assert boosted > fast


def test_speaker_variant_sets_sid(driver):
    driver._voice = "en_US-libritts-high"
    driver._variant = "2"
    seg = driver._build_job(["hi"])["segments"][0]
    assert seg["sid"] == 2


def test_available_variants_multispeaker(driver):
    driver._voice = "en_US-libritts-high"
    variants = driver._getAvailableVariants()
    assert len(variants) == 3
    assert "0" in variants and "2" in variants


def test_available_variants_single_speaker(driver):
    variants = driver._getAvailableVariants()
    assert list(variants.keys()) == ["0"]


def test_available_voices(driver):
    voices = driver._getAvailableVoices()
    assert "en_US-lessac-medium" in voices
    assert voices["fr_FR-siwis-medium"].language == "fr_FR"


def _scales(driver):
    return driver._build_job(["hi"])["segments"][0]["scales"]


def test_expressiveness_drives_both_noise_parameters(driver):
    # 50 is the voice as trained; the helper multiplies its noise scales.
    assert _scales(driver) == {"noiseScale": 1.0, "noiseW": 1.0,
                               "lengthScale": 1.0}
    driver._variance = 0
    flat = _scales(driver)
    assert flat["noiseScale"] < 1.0 and flat["noiseW"] == flat["noiseScale"]
    # Simple mode never touches the model's pace.
    assert flat["lengthScale"] == 1.0
    driver._variance = 100
    assert _scales(driver)["noiseScale"] > 1.0


def test_advanced_mode_sets_each_parameter_directly(driver):
    driver._advancedMode = True
    # Advanced defaults are also "as trained", so switching modes at the
    # defaults does not change how the voice sounds.
    assert _scales(driver) == {"noiseScale": 1.0, "noiseW": 1.0,
                               "lengthScale": 1.0}
    driver._noiseScale = 25
    driver._noiseW = 75
    driver._lengthScale = 100
    assert _scales(driver) == {"noiseScale": 0.5, "noiseW": 1.5,
                               "lengthScale": 2.0}
    # Expressiveness is ignored while advanced mode is on.
    driver._variance = 0
    assert _scales(driver)["noiseScale"] == 0.5


def test_advanced_settings_replace_expressiveness_in_the_ui(driver):
    ids = [s.id for s in driver._get_supportedSettings()]
    assert "variance" in ids
    assert "noiseScale" not in ids
    assert "advancedMode" in ids

    driver._advancedMode = True
    ids = [s.id for s in driver._get_supportedSettings()]
    assert ids[-3:] == ["noiseScale", "noiseW", "lengthScale"]
    assert "variance" not in ids


def test_assigned_language_voice_beats_the_default(driver):
    # Two English voices are installed; without an assignment the first one
    # wins, and with one the assigned voice does.
    seq = [LangChangeCommand("en_US"), "hello"]
    default = driver._build_job(seq)["segments"][0]["modelPath"]
    assert default.endswith("en_US-lessac-medium.onnx")

    driver._lang_voices = {"en_us": "en_US-libritts-high"}
    assigned = driver._build_job(seq)["segments"][0]["modelPath"]
    assert assigned.endswith("en_US-libritts-high.onnx")


def test_assignment_to_a_missing_voice_is_ignored(driver):
    driver._lang_voices = {"fr_fr": "fr_FR-uninstalled-low"}
    seg = driver._build_job([LangChangeCommand("fr_FR"), "bonjour"])["segments"][0]
    assert seg["modelPath"].endswith("fr_FR-siwis-medium.onnx")


def test_phoneme_command_is_sent_as_phonemes(driver):
    job = driver._build_job(["say ", PhonemeCommand("t\u0259\u02c8me\u026ato\u028a",
                                                    text="tomato"), " now"])
    kinds = [(seg["text"], seg["ipa"]) for seg in job["segments"]]
    assert kinds == [("say ", False),
                     ("t\u0259\u02c8me\u026ato\u028a", True),
                     (" now", False)]
    phoneme_segment = job["segments"][1]
    # The word it stood for travels with it, for a voice missing a phoneme.
    assert phoneme_segment["fallbackText"] == "tomato"
    # Prosody and voice still come from the surrounding speech.
    assert phoneme_segment["modelPath"] == job["segments"][0]["modelPath"]
    assert phoneme_segment["volume"] == job["segments"][0]["volume"]


def test_phoneme_command_without_ipa_speaks_its_text(driver):
    job = driver._build_job([PhonemeCommand("", text="tomato")])
    assert [(s["text"], s["ipa"]) for s in job["segments"]] == [("tomato", False)]


def test_phoneme_command_with_nothing_at_all_is_dropped(driver):
    assert driver._build_job([PhonemeCommand("", text=None)])["segments"] == []


def test_sentence_pause_reaches_the_segment(driver):
    assert driver._build_job(["hi"])["segments"][0]["sentencePauseMs"] == 100
    driver._sentencePause = 0
    assert driver._build_job(["hi"])["segments"][0]["sentencePauseMs"] == 0
    driver._sentencePause = 100
    assert driver._build_job(["hi"])["segments"][0]["sentencePauseMs"] == 400


class _LogRecorder:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


def _fake_windows(build):
    class Version:
        pass

    version = Version()
    version.build = build
    return lambda: version


def test_windows_11_produces_no_warning(monkeypatch):
    recorder = _LogRecorder()
    monkeypatch.setattr(piper, "log", recorder)
    # 22000 is the first Windows 11 build; 26100 is a current one.
    monkeypatch.setattr(piper.sys, "getwindowsversion", _fake_windows(26100),
                        raising=False)
    piper._warn_if_unsupported_windows()
    assert recorder.warnings == []


def test_older_windows_is_named_in_the_log(monkeypatch):
    recorder = _LogRecorder()
    monkeypatch.setattr(piper, "log", recorder)
    # 19045 is Windows 10 22H2: it runs, but it is not supported.
    monkeypatch.setattr(piper.sys, "getwindowsversion", _fake_windows(19045),
                        raising=False)
    piper._warn_if_unsupported_windows()
    assert len(recorder.warnings) == 1
    assert "19045" in recorder.warnings[0]
    assert "Windows 11" in recorder.warnings[0]


class _FakeHelper:
    """Records the frames the driver would send to the helper process."""

    def __init__(self):
        self.sent = []

    def send(self, msg_type, payload):
        self.sent.append((msg_type, payload))

    def types(self):
        return [msg_type for msg_type, _payload in self.sent]

    def payload(self, msg_type):
        for sent_type, payload in self.sent:
            if sent_type == msg_type:
                return payload
        raise AssertionError("no %r frame was sent" % msg_type)


@pytest.fixture
def wired(driver, tmp_path, monkeypatch):
    """A driver with a fake helper and a voice file that exists on disk."""
    from synthDrivers.piper import _paths, _warmup
    model = tmp_path / "en_US-lessac-medium.onnx"
    model.write_bytes(b"")
    monkeypatch.setattr(_paths, "voice_model_path", lambda key: str(model))
    monkeypatch.setattr(_warmup, "load", lambda: ["Inbox", "stand by"])
    driver._helper = _FakeHelper()
    driver._useCache = True
    driver._warmup_words = ["Inbox"]
    return driver


def test_warmup_request_carries_the_users_phrases(wired):
    wired._request_warmup()
    payload = wired._helper.payload(proto.LOAD_VOICE)
    assert payload["extraWords"] == ["Inbox"]
    assert payload["scales"] == {"noiseScale": 1.0, "noiseW": 1.0,
                                 "lengthScale": 1.0}


def test_turning_the_cache_off_stops_preparing(wired):
    wired._set_useCache(False)
    assert wired._helper.payload(proto.SET_CACHE) == {"enabled": False}
    # Nothing is prepared for a cache that is not being read.
    assert proto.LOAD_VOICE not in wired._helper.types()


def test_turning_the_cache_on_prepares_again(wired):
    wired._useCache = False
    wired._set_useCache(True)
    assert wired._helper.payload(proto.SET_CACHE) == {"enabled": True}
    assert proto.LOAD_VOICE in wired._helper.types()


def test_rebuilding_clears_then_prepares(wired):
    wired.rebuild_cache()
    assert wired._helper.types() == [proto.CLEAR_CACHE, proto.LOAD_VOICE]


def test_rebuilding_with_the_cache_off_only_clears(wired):
    wired._useCache = False
    wired.rebuild_cache()
    assert wired._helper.types() == [proto.CLEAR_CACHE]


def test_reloading_phrases_picks_up_the_saved_list(wired):
    wired.reload_warmup_words()
    assert wired._warmup_words == ["Inbox", "stand by"]
    assert wired._helper.payload(proto.LOAD_VOICE)["extraWords"] == [
        "Inbox", "stand by"]


def test_lone_symbols_are_given_their_spoken_name(driver):
    """espeak produces no phonemes at all for a lone full stop, so a
    character read or typed has to reach the helper as a name."""
    job = driver._build_job([CharacterModeCommand(True), "."])
    assert [s["text"] for s in job["segments"]] == ["dot"]
    assert job["segments"][0]["charMode"] is True


def test_a_typed_space_is_still_spoken(driver):
    job = driver._build_job([CharacterModeCommand(True), " "])
    assert [s["text"] for s in job["segments"]] == ["space"]


def test_letters_and_digits_are_left_alone(driver):
    for text in ("a", "Z", "7"):
        job = driver._build_job([CharacterModeCommand(True), text])
        assert [s["text"] for s in job["segments"]] == [text]


def test_symbol_names_follow_the_document_language(driver):
    job = driver._build_job([LangChangeCommand("fr"), CharacterModeCommand(True), ","])
    assert [s["text"] for s in job["segments"]] == ["virgule"]


def test_ordinary_text_is_never_renamed(driver):
    # Only single characters in character mode are looked up.
    job = driver._build_job(["."])
    assert [s["text"] for s in job["segments"]] == ["."]
    job = driver._build_job([CharacterModeCommand(True), ".."])
    assert [s["text"] for s in job["segments"]] == [".."]


def test_a_symbol_nvda_cannot_name_is_passed_through(driver):
    job = driver._build_job([CharacterModeCommand(True), "\u2603"])
    assert [s["text"] for s in job["segments"]] == ["\u2603"]


# -- settings remembered per voice ------------------------------------------

def test_settings_follow_the_voice_they_were_made_for(wired):
    """Rate and pitch that suit a fast low-quality voice rarely suit a slow
    high-quality one, and NVDA keeps settings per synthesizer, not per voice."""
    wired._rate = 80
    wired._pitch = 30
    wired._set_voice("fr_FR-siwis-medium")
    # A voice with nothing remembered inherits what is set, so arriving at it
    # never changes how it sounds.
    assert (wired._rate, wired._pitch) == (80, 30)

    wired._rate = 40
    wired._set_voice("en_US-lessac-medium")
    assert (wired._rate, wired._pitch) == (80, 30)

    wired._set_voice("fr_FR-siwis-medium")
    assert wired._rate == 40


def test_the_speaker_of_a_multi_speaker_voice_is_remembered(wired):
    wired._set_voice("en_US-libritts-high")
    wired._variant = "2"
    wired._set_voice("en_US-lessac-medium")
    wired._set_voice("en_US-libritts-high")
    assert wired._variant == "2"


def test_turning_the_memory_off_leaves_settings_alone(wired):
    wired._rate = 90
    wired._set_voice("fr_FR-siwis-medium")
    wired._rate = 20
    wired._set_voice("en_US-lessac-medium")

    wired._rememberPerVoice = False
    wired._rate = 55
    wired._set_voice("fr_FR-siwis-medium")
    assert wired._rate == 55


def test_settings_are_written_to_disk_on_a_voice_change(wired):
    from synthDrivers.piper import _voicesettings
    wired._rate = 33
    wired._set_voice("fr_FR-siwis-medium")
    stored, _favorites = _voicesettings.load()
    assert stored["en_US-lessac-medium"]["rate"] == 33


def test_rate_boost_reaches_much_further_than_the_plain_rate(driver):
    _speed, plain = driver._rate_to_stretch(100)
    driver._rateBoost = True
    _speed, boosted = driver._rate_to_stretch(100)
    # Boost is opt-in, so it can go far beyond the ordinary top speed.
    assert plain == 2.0
    assert boosted >= 4.0
    # And it still does nothing at the bottom of the range.
    driver._rateBoost = False
    _speed, slow = driver._rate_to_stretch(0)
    driver._rateBoost = True
    assert driver._rate_to_stretch(0)[1] == slow
