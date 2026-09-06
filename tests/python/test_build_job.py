"""Tests for Piper speech-sequence -> SPEAK job conversion."""

import threading

import pytest

import synthDrivers.piper as piper
from synthDrivers.piper import _paths, _voices
from speech.commands import (
    BreakCommand, CharacterModeCommand, IndexCommand, LangChangeCommand,
    PitchCommand, RateCommand,
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
