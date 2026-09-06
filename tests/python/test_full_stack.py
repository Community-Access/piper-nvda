"""End-to-end test of the Piper Python plumbing against the real helper:
speaking a phrase and playing a demo mp3. Skipped if build/assets missing."""

import json
import os
import threading

import pytest

from synthDrivers.piper import _helperProc, _audio, _protocol as proto

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HELPER = os.path.join(ROOT, "helper", "target", "release", "piper-helper.exe")
ASSETS = os.path.join(ROOT, "assets")
MODEL = os.path.join(ASSETS, "lessac-medium.onnx")
SAMPLE = os.path.join(ASSETS, "sample_lessac.mp3")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(HELPER) and os.path.exists(MODEL)),
    reason="helper build or assets missing",
)

SOURCE_DIR = os.path.join(ROOT, "helper", "src")


def _newest_source_time():
    newest = 0.0
    for base, _dirs, files in os.walk(SOURCE_DIR):
        for name in files:
            if name.endswith(".rs"):
                newest = max(newest, os.path.getmtime(os.path.join(base, name)))
    return newest


def test_helper_binary_is_not_stale():
    """A stale helper ignores protocol messages it does not know, silently.

    That turns "the feature works" into "the old binary did something else",
    which is exactly how a cache test once passed for the wrong reason. Every
    other test in this file trusts the binary, so check it first.
    """
    assert os.path.getmtime(HELPER) >= _newest_source_time(), (
        "piper-helper.exe is older than helper/src; run "
        "cargo build --release --manifest-path helper/Cargo.toml")


class FakePlayer:
    def __init__(self):
        self.fed_bytes = 0
        self.idled = 0

    def feed(self, data, onDone=None):
        self.fed_bytes += len(data)
        if onDone is not None:
            onDone()

    def idle(self):
        self.idled += 1

    def stop(self):
        pass

    def pause(self, s):
        pass

    def close(self):
        pass


def _espeak_args():
    return ["--espeak-dll", os.path.join(ASSETS, "espeak-ng", "eSpeak NG",
                                         "libespeak-ng.dll"),
            "--espeak-data", os.path.join(ASSETS, "espeak-ng", "eSpeak NG")]


def test_speak_via_stack():
    player = FakePlayer()
    indexes = []
    done = threading.Event()
    pump = _audio.AudioPump(player, indexes.append, done.set)
    hello = threading.Event()

    def on_frame(mt, payload):
        if mt == proto.HELLO:
            hello.set()
        elif mt in (proto.AUDIO, proto.MARKER, proto.DONE):
            pump.handle_frame(mt, payload)

    helper = _helperProc.HelperProcess(HELPER, _espeak_args(), on_frame=on_frame)
    helper.start()
    assert hello.wait(30)
    job = {
        "utteranceId": 1,
        "segments": [{"text": "Testing Piper.", "modelPath": MODEL, "sid": 0,
                      "indexesBefore": [11]}],
        "indexesAfter": [22],
    }
    helper.send(proto.SPEAK, job)
    assert done.wait(60)
    assert player.fed_bytes > 4000
    assert set(indexes) >= {11, 22}
    helper.terminate()
    pump.shutdown()


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="no demo sample")
def test_play_demo_sample():
    player = FakePlayer()
    done = threading.Event()
    pump = _audio.AudioPump(player, lambda i: None, done.set)
    hello = threading.Event()

    def on_frame(mt, payload):
        if mt == proto.HELLO:
            hello.set()
        elif mt in (proto.AUDIO, proto.MARKER, proto.DONE):
            pump.handle_frame(mt, payload)

    helper = _helperProc.HelperProcess(HELPER, _espeak_args(), on_frame=on_frame)
    helper.start()
    assert hello.wait(30)
    helper.send(proto.PLAY_SAMPLE, {"path": SAMPLE})
    assert done.wait(30)
    assert player.fed_bytes > 10000  # decoded mp3 produced audio
    helper.terminate()
    pump.shutdown()


class RecordingPlayer(FakePlayer):
    """Keeps the audio it is fed so tests can compare two utterances."""

    def __init__(self):
        super().__init__()
        self.audio = bytearray()

    def feed(self, data, onDone=None):
        self.audio += bytes(data)
        super().feed(data, onDone)


class _Session:
    """A helper process wired to a pump, for tests that speak more than once."""

    def __init__(self):
        self.player = RecordingPlayer()
        self.done = threading.Event()
        self.errors = []
        self.pump = _audio.AudioPump(self.player, lambda i: None, self.done.set)
        hello = threading.Event()

        def on_frame(mt, payload):
            if mt == proto.HELLO:
                hello.set()
            elif mt == proto.ERROR:
                self.errors.append(proto.parse_json(payload))
            elif mt in (proto.AUDIO, proto.MARKER, proto.DONE):
                self.pump.handle_frame(mt, payload)

        self.helper = _helperProc.HelperProcess(HELPER, _espeak_args(),
                                                on_frame=on_frame)
        self.helper.start()
        assert hello.wait(30)

    def say(self, text, **segment):
        """Speak `text` and return exactly the audio it produced."""
        before = len(self.player.audio)
        self.done.clear()
        segment.update(text=text, modelPath=MODEL)
        self.helper.send(proto.SPEAK, {
            "utteranceId": 1,
            "segments": [segment],
            "indexesAfter": [],
        })
        assert self.done.wait(60)
        return bytes(self.player.audio[before:])

    def close(self):
        self.helper.terminate()
        self.pump.shutdown()


def test_pronunciation_override_changes_the_audio():
    """A lexicon entry must reach the model, not just the config file."""
    session = _Session()
    try:
        plain = session.say("nvda")
        assert plain

        session.helper.send(proto.SET_LEXICON, {
            "rev": 1,
            "entries": {"nvda": "\u025bn vi\u02d0 di\u02d0 \u02c8e\u026a"},
        })
        overridden = session.say("nvda")
        assert overridden != plain

        # A word with no entry is unaffected by the lexicon.
        assert session.say("hello") == session.say("hello")

        # Clearing the lexicon restores the original pronunciation, served
        # from the cache entry made before any override existed.
        session.helper.send(proto.SET_LEXICON, {"rev": 2, "entries": {}})
        assert session.say("nvda") == plain
    finally:
        session.close()


def test_inference_parameters_are_cached_separately():
    """The scales are part of the cache key, so the same text at different
    settings must be synthesized again rather than replayed."""
    session = _Session()
    try:
        default = session.say("Testing expressiveness.")
        flat = session.say("Testing expressiveness.",
                           scales={"noiseScale": 0.4, "noiseW": 0.4})
        assert default and flat != default

        # length_scale changes the model's pace, so the audio gets longer.
        slow = session.say("Testing expressiveness.",
                           scales={"lengthScale": 1.5})
        assert len(slow) > len(default) * 1.2, (len(default), len(slow))

        # The original setting still hits its own cache entry unchanged.
        assert session.say("Testing expressiveness.") == default
    finally:
        session.close()


def test_phoneme_command_audio_differs_from_the_text():
    """A pronunciation sent as phonemes must reach the model as phonemes."""
    session = _Session()
    try:
        spoken = session.say("tomato")
        as_phonemes = session.say("təˈmɑːtoʊ", ipa=True)
        assert spoken and as_phonemes
        assert as_phonemes != spoken

        # Phonemes the voice does not have fall back to the word they stood
        # for, rather than going silent. The model's duration predictor is
        # stochastic, so two runs of the same phonemes differ by a few per
        # cent; compare duration rather than bytes.
        fallback = session.say("███", ipa=True,
                               fallbackText="tomato")
        assert fallback
        assert abs(len(fallback) - len(spoken)) < len(spoken) * 0.3, (
            len(spoken), len(fallback))

        # Without a fallback the same unknown phonemes produce nothing.
        assert session.say("████", ipa=True) == b""
    finally:
        session.close()


def test_sentence_pause_lengthens_the_gap_between_sentences():
    session = _Session()
    try:
        text = "One. Two. Three."
        tight = session.say(text, sentencePauseMs=0)
        spaced = session.say(text, sentencePauseMs=400)
        assert tight and spaced
        # Two sentence boundaries at 400 ms each, at 22050 Hz, 16-bit mono.
        expected = 2 * int(0.4 * 22050) * 2
        assert abs((len(spaced) - len(tight)) - expected) < expected * 0.1, (
            len(tight), len(spaced))
    finally:
        session.close()


def test_a_voice_needing_another_phonemizer_is_refused():
    """Six published voices are not phonemized by espeak. Feeding them
    espeak's IPA would produce confident nonsense, so the helper refuses."""
    voice_dir = os.path.join(ROOT, "build", "test_voices")
    os.makedirs(voice_dir, exist_ok=True)
    fake_model = os.path.join(voice_dir, "fake-pinyin.onnx")
    # The model itself is never opened: refusing a voice must not cost a
    # model load, so an empty file is enough to prove the config decided.
    with open(fake_model, "wb") as f:
        f.write(b"")
    with open(MODEL + ".json", encoding="utf-8") as f:
        config = json.load(f)
    config["phoneme_type"] = "pinyin"
    with open(fake_model + ".json", "w", encoding="utf-8") as f:
        json.dump(config, f)

    session = _Session()
    try:
        session.done.clear()
        session.helper.send(proto.SPEAK, {
            "utteranceId": 1,
            "segments": [{"text": "ni hao", "modelPath": fake_model}],
            "indexesAfter": [],
        })
        # It still finishes, so speech never stalls.
        assert session.done.wait(60)
        assert session.player.audio == b""
        assert any(e.get("code") == "unsupportedVoice" for e in session.errors),             session.errors
        assert any("pinyin" in e.get("message", "") for e in session.errors)
    finally:
        session.close()
        for path in (fake_model, fake_model + ".json"):
            if os.path.exists(path):
                os.remove(path)


def test_cache_can_be_switched_off_and_rebuilt():
    """A cache hit replays exactly; a miss goes back to the model.

    The duration predictor is stochastic, so re-synthesized audio is never
    byte-identical. That is what makes "was this cached?" observable.
    """
    session = _Session()
    try:
        first = session.say("Cache test.")
        assert first
        # Identical bytes can only come from the cache.
        assert session.say("Cache test.") == first

        session.helper.send(proto.SET_CACHE, {"enabled": False})
        off_once = session.say("Cache test.")
        assert off_once != first
        assert session.say("Cache test.") != off_once

        # Switching it back on finds the entry made before it was disabled,
        # so nothing was thrown away while it was off.
        session.helper.send(proto.SET_CACHE, {"enabled": True})
        assert session.say("Cache test.") == first

        # Rebuilding does throw it away.
        session.helper.send(proto.CLEAR_CACHE, {})
        rebuilt = session.say("Cache test.")
        assert rebuilt != first
        # And the rebuilt entry is cached in its turn.
        assert session.say("Cache test.") == rebuilt

        # A malformed control message must not wedge the worker.
        session.helper.send(proto.SET_CACHE, {"nonsense": True})
        assert session.say("Cache test.") == rebuilt
    finally:
        session.close()


def test_a_lone_punctuation_character_is_never_silent():
    """espeak-ng reads a punctuation character on its own as clause
    punctuation and returns no phonemes, so the helper has to fall back to
    the character's name. Silence here is a character the user cannot read."""
    session = _Session()
    try:
        for text in (".", ",", " ", "(", "?", "-", "'"):
            audio = session.say(text, charMode=True)
            assert audio, "silent for %r" % text
        # A character espeak can voice is spoken directly, not renamed.
        assert session.say("a", charMode=True)

        # A full stop really is spoken as its name: the same length as the
        # word, not the length of some other sound. Two syntheses are never
        # byte-identical, so compare duration.
        as_symbol = session.say(".", charMode=True)
        as_word = session.say("dot")
        assert abs(len(as_symbol) - len(as_word)) < len(as_word) * 0.3, (
            len(as_symbol), len(as_word))
    finally:
        session.close()
