"""Tests for Piper speech-sequence -> SPEAK job conversion."""

import threading

import pytest

import synthDrivers.piper as piper
from synthDrivers.piper import _paths, _voices
from speech.commands import (
    BreakCommand, CharacterModeCommand, IndexCommand, LangChangeCommand,
    PhonemeCommand, PitchCommand, RateCommand,
)


def _voice(key, lang, num_speakers=1, speaker_map=None):
    return _voices.InstalledVoice(
        key=key, display_name=key, language=lang, espeak_lang="en-us",
        num_speakers=num_speakers, speaker_id_map=speaker_map or {})


@pytest.fixture
def driver():
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
