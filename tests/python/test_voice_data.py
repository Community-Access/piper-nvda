"""Tests for the on-disk data the add-on manages: the pronunciation lexicon,
per-language voice assignments, and importing voices from other add-ons."""

import json
import os
import tarfile

import pytest

from synthDrivers.piper import (
    _download,
    _import,
    _langvoices,
    _lexicon,
    _paths,
    _phonemes,
    _voices,
    _warmup,
)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Point the add-on's data directory at a temporary tree."""
    monkeypatch.setenv("PIPER_DATA_DIR", str(tmp_path / "config"))
    return tmp_path


def _make_voice(directory, key, model_name=None, phoneme_type=None):
    """Write a minimal voice (model plus config) into `directory`."""
    os.makedirs(directory, exist_ok=True)
    model = os.path.join(directory, (model_name or key) + ".onnx")
    with open(model, "wb") as f:
        f.write(b"onnx-model-bytes")
    config = {"audio": {"sample_rate": 22050}, "espeak": {"voice": "en-us"}}
    if phoneme_type is not None:
        config["phoneme_type"] = phoneme_type
    with open(model + ".json", "w", encoding="utf-8") as f:
        json.dump(config, f)
    return model


# -- lexicon ---------------------------------------------------------------

def test_lexicon_starts_empty():
    assert _lexicon.load() == (0, {})


def test_lexicon_save_normalizes_and_bumps_revision():
    rev, entries = _lexicon.save({"  NVDA ": " ɛnvidiːeɪ ",
                                  "blank": "   ", "": "x"})
    assert rev == 1
    assert entries == {"nvda": "ɛnvidiːeɪ"}
    assert _lexicon.load() == (1, entries)
    rev2, _ = _lexicon.save(entries)
    assert rev2 == 2


def test_lexicon_survives_a_damaged_file():
    os.makedirs(_paths.data_dir(), exist_ok=True)
    with open(_lexicon.path(), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert _lexicon.load() == (0, {})


def test_lexicon_message_shape():
    assert _lexicon.message(3, {"a": "b"}) == {"rev": 3, "entries": {"a": "b"}}


# -- language voices -------------------------------------------------------

def test_language_voices_roundtrip():
    _langvoices.save({"en-US": "en_US-lessac-medium", "": "ignored",
                      "fr": ""})
    assert _langvoices.load() == {"en_us": "en_US-lessac-medium"}


def test_language_voices_resolution_falls_back_to_primary_subtag():
    mapping = {"pt": "pt_BR-faber-medium", "en_gb": "en_GB-alan-low"}
    installed = {"pt_BR-faber-medium", "en_GB-alan-low"}
    assert _langvoices.resolve(mapping, "pt-BR", installed) == "pt_BR-faber-medium"
    assert _langvoices.resolve(mapping, "en_GB", installed) == "en_GB-alan-low"
    assert _langvoices.resolve(mapping, "de", installed) is None
    assert _langvoices.resolve(mapping, "", installed) is None


def test_language_voices_ignores_uninstalled_assignments():
    mapping = {"en_us": "gone-voice"}
    assert _langvoices.resolve(mapping, "en_US", set()) is None


# -- importing from other add-ons -----------------------------------------

def test_discover_finds_sonata_and_dengjen_voices(tmp_path):
    config = tmp_path / "config"
    _make_voice(str(config / "sonata" / "voices" / "piper" / "en_US-lessac-medium"),
                "en_US-lessac-medium")
    # Dengjen keeps the same layout; some voices name the model generically.
    _make_voice(str(config / "dengjen" / "voices" / "piper" / "fr_FR-siwis-low"),
                "fr_FR-siwis-low", model_name="model")

    found = _import.discover(str(config))
    assert [v.key for v in found] == ["en_US-lessac-medium", "fr_FR-siwis-low"]
    assert {v.source for v in found} == {"Sonata Neural Voices",
                                         "Dengjen Neural Voices"}
    assert all(not v.installed for v in found)
    assert found[0].size == len(b"onnx-model-bytes")


def test_discover_skips_models_without_a_config(tmp_path):
    config = tmp_path / "config"
    stray = config / "sonata" / "voices" / "piper" / "broken"
    os.makedirs(stray)
    (stray / "broken.onnx").write_bytes(b"x")
    assert _import.discover(str(config)) == []


def test_import_copies_voices_and_reports_installed(tmp_path):
    config = tmp_path / "config"
    _make_voice(str(config / "sonata" / "voices" / "piper" / "en_US-lessac-medium"),
                "en_US-lessac-medium")
    found = _import.discover(str(config))

    progress = []
    assert _import.import_voices(found, progress=lambda d, t: progress.append((d, t))) \
        == ["en_US-lessac-medium"]
    assert progress == [(1, 1)]
    assert _paths.voice_installed("en_US-lessac-medium")
    assert found[0].installed

    # Importing again is a no-op rather than a duplicate copy.
    assert _import.import_voices(_import.discover(str(config))) == []


def test_install_from_archive(tmp_path):
    source = tmp_path / "src"
    model = _make_voice(str(source), "en_US-ryan-high")
    archive = tmp_path / "voice.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(model, arcname="en_US-ryan-high/en_US-ryan-high.onnx")
        tar.add(model + ".json",
                arcname="en_US-ryan-high/en_US-ryan-high.onnx.json")

    assert _import.install_from_file(str(archive)) == ["en_US-ryan-high"]
    assert _paths.voice_installed("en_US-ryan-high")


def test_archive_path_traversal_is_rejected(tmp_path):
    escape = tmp_path / "evil.onnx"
    escape.write_bytes(b"pwned")
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(escape, arcname="../../evil.onnx")

    with pytest.raises(_import.VoiceImportError):
        _import.install_from_file(str(archive))
    assert not os.path.exists(os.path.join(_paths.voices_dir(), "evil.onnx"))


def test_archive_without_a_pair_is_rejected(tmp_path):
    lonely = tmp_path / "lonely.onnx"
    lonely.write_bytes(b"x")
    archive = tmp_path / "lonely.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(lonely, arcname="lonely.onnx")

    with pytest.raises(_import.VoiceImportError):
        _import.install_from_file(str(archive))
    # The half-extracted file must not be left behind.
    assert os.listdir(_paths.voices_dir()) == []


def test_install_from_model_file(tmp_path):
    model = _make_voice(str(tmp_path / "downloads"), "de_DE-thorsten-medium")
    assert _import.install_from_file(model) == ["de_DE-thorsten-medium"]
    assert _paths.voice_installed("de_DE-thorsten-medium")


def test_install_from_model_without_config_is_rejected(tmp_path):
    model = tmp_path / "alone.onnx"
    model.write_bytes(b"x")
    with pytest.raises(_import.VoiceImportError):
        _import.install_from_file(str(model))


def test_unsupported_file_type_is_rejected(tmp_path):
    other = tmp_path / "voice.zip"
    other.write_bytes(b"x")
    with pytest.raises(_import.VoiceImportError):
        _import.install_from_file(str(other))


# -- voices needing a phonemizer we do not bundle --------------------------

def test_phoneme_type_defaults_to_espeak(tmp_path):
    # 47 published voices predate the field, and all of them are espeak.
    model = _make_voice(str(tmp_path), "old_voice")
    assert _phonemes.phoneme_type(model + ".json") == "espeak"
    assert _phonemes.is_supported(model + ".json")


def test_phoneme_type_reads_the_config(tmp_path):
    model = _make_voice(str(tmp_path), "zh_voice", phoneme_type="pinyin")
    assert _phonemes.phoneme_type(model + ".json") == "pinyin"
    assert not _phonemes.is_supported(model + ".json")
    # Code-point voices need no phonemizer at all, so they are supported.
    text_model = _make_voice(str(tmp_path), "uk_voice", phoneme_type="text")
    assert _phonemes.is_supported(text_model + ".json")


def test_phoneme_type_survives_a_damaged_config(tmp_path):
    bad = tmp_path / "bad.onnx.json"
    bad.write_text("{not json", encoding="utf-8")
    assert _phonemes.phoneme_type(str(bad)) == "espeak"
    assert _phonemes.phoneme_type(str(tmp_path / "missing.json")) == "espeak"


def test_unsupported_voices_are_not_offered_as_installed(tmp_path):
    _make_voice(_paths.voices_dir(), "en_US-lessac-medium")
    _make_voice(_paths.voices_dir(), "zh_CN-xiao_ya-medium",
                phoneme_type="pinyin")
    keys = [v.key for v in _voices.load_installed()]
    assert keys == ["en_US-lessac-medium"]


def test_unsupported_voices_are_not_imported(tmp_path):
    config = tmp_path / "config"
    _make_voice(str(config / "sonata" / "voices" / "piper" / "th_TH-tsync2-medium"),
                "th_TH-tsync2-medium", phoneme_type="thai")
    found = _import.discover(str(config))
    assert len(found) == 1 and not found[0].supported
    assert _import.import_voices(found) == []
    assert not _paths.voice_installed("th_TH-tsync2-medium")


def test_unsupported_archive_is_rejected(tmp_path):
    source = tmp_path / "src"
    model = _make_voice(str(source), "he_IL-saspeech-medium",
                        phoneme_type="hebrew")
    archive = tmp_path / "voice.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(model, arcname="he_IL-saspeech-medium.onnx")
        tar.add(model + ".json", arcname="he_IL-saspeech-medium.onnx.json")

    with pytest.raises(_import.VoiceImportError):
        _import.install_from_file(str(archive))
    assert not _paths.voice_installed("he_IL-saspeech-medium")
    # Nothing half-extracted is left behind.
    assert os.listdir(_paths.voices_dir()) == []


def test_unsupported_model_file_is_rejected(tmp_path):
    model = _make_voice(str(tmp_path / "downloads"), "ja_JA-hi_fi_captain-medium",
                        phoneme_type="japanese")
    with pytest.raises(_import.VoiceImportError):
        _import.install_from_file(model)


def test_download_checks_the_config_before_fetching_the_model(tmp_path):
    """The config is small and says which phonemizer the voice needs, so an
    unusable voice must be refused before its model is downloaded."""
    requested = []

    class Voice:
        key = "zh_CN-xiao_ya-medium"
        name = "xiao_ya"
        model_url = "http://example/model.onnx"
        config_url = "http://example/model.onnx.json"
        model_md5 = None
        config_md5 = None
        model_size = 60_000_000

    config = json.dumps({"audio": {"sample_rate": 22050},
                         "espeak": {"voice": "cmn"},
                         "phoneme_type": "pinyin"}).encode("utf-8")

    class Response:
        def __init__(self, data):
            self._data = data
            self.status = 200
            self.headers = {"Content-Length": str(len(data))}

        def read(self, n):
            data, self._data = self._data[:n], self._data[n:]
            return data

    def opener(request):
        url = getattr(request, "full_url", request)
        requested.append(url)
        return Response(config if url.endswith(".json") else b"x" * 100)

    with pytest.raises(_download.UnsupportedVoice) as excinfo:
        _download.download_voice(Voice(), opener=opener)
    assert "xiao_ya" in str(excinfo.value)
    assert requested == ["http://example/model.onnx.json"]
    assert not os.path.isfile(_paths.voice_config_path(Voice.key))
    assert not os.path.isfile(_paths.voice_model_path(Voice.key))


# -- extra phrases to prepare ----------------------------------------------

def test_warmup_starts_empty_and_round_trips():
    assert _warmup.load() == []
    assert _warmup.save(["Inbox", "Teams"]) == ["Inbox", "Teams"]
    assert _warmup.load() == ["Inbox", "Teams"]


def test_warmup_normalizes_whitespace_and_duplicates():
    saved = _warmup.save(["  Inbox  ", "in a  moment", "INBOX", "", "   "])
    # Order is the order the user gave, case-insensitive duplicates dropped.
    assert saved == ["Inbox", "in a moment"]


def test_warmup_rejects_phrases_too_long_to_help():
    # Longer than the helper's first-chunk target, so it would be split
    # before it was ever looked up.
    too_long = "x" * (_warmup.MAX_LENGTH + 1)
    assert _warmup.clean([too_long]) == []
    just_right = "y" * _warmup.MAX_LENGTH
    assert _warmup.clean([just_right]) == [just_right]


def test_warmup_caps_the_list():
    many = ["phrase %d" % i for i in range(_warmup.MAX_ENTRIES + 50)]
    assert len(_warmup.clean(many)) == _warmup.MAX_ENTRIES


def test_warmup_survives_a_damaged_file():
    os.makedirs(_paths.data_dir(), exist_ok=True)
    with open(_warmup.path(), "w", encoding="utf-8") as f:
        f.write("[not json")
    assert _warmup.load() == []


# -- per-voice settings and favourites -------------------------------------

def test_voice_settings_round_trip():
    from synthDrivers.piper import _voicesettings
    assert _voicesettings.load() == ({}, [])
    _voicesettings.save({"en_US-lessac-medium": {"rate": 70, "pitch": 40}},
                        ["en_US-lessac-medium"])
    voices, favorites = _voicesettings.load()
    assert voices == {"en_US-lessac-medium": {"rate": 70, "pitch": 40}}
    assert favorites == ["en_US-lessac-medium"]


def test_voice_settings_ignore_unknown_fields():
    from synthDrivers.piper import _voicesettings
    _voicesettings.save({"v": {"rate": 10, "nonsense": 1}}, [])
    voices, _fav = _voicesettings.load()
    assert voices == {"v": {"rate": 10}}


def test_voice_settings_survive_a_damaged_file():
    from synthDrivers.piper import _voicesettings
    os.makedirs(_paths.data_dir(), exist_ok=True)
    with open(_voicesettings.path(), "w", encoding="utf-8") as f:
        f.write("not json at all")
    assert _voicesettings.load() == ({}, [])


def test_next_favorite_cycles_the_favourites():
    from synthDrivers.piper import _voicesettings
    installed = {"a", "b", "c"}
    favorites = ["a", "c"]
    assert _voicesettings.next_favorite(favorites, installed, "a") == "c"
    assert _voicesettings.next_favorite(favorites, installed, "c") == "a"
    # A voice outside the ring moves into it rather than going nowhere.
    assert _voicesettings.next_favorite(favorites, installed, "b") == "a"


def test_next_favorite_falls_back_to_every_installed_voice():
    from synthDrivers.piper import _voicesettings
    installed = {"a", "b"}
    # Useful before anyone has chosen a favourite.
    assert _voicesettings.next_favorite([], installed, "a") == "b"
    # And there is nowhere to go with only one voice.
    assert _voicesettings.next_favorite([], {"a"}, "a") is None
    # Favourites that are no longer installed do not make a ring.
    assert _voicesettings.next_favorite(["gone"], {"a"}, "a") is None


# -- backup, restore, reset -------------------------------------------------

def test_backup_and_restore_round_trip(tmp_path):
    from synthDrivers.piper import _backup, _lexicon, _voicesettings
    _lexicon.save({"nvda": "ɛnviːdiːˈeɪ"})
    _voicesettings.save({"v": {"rate": 80}}, ["v"])
    archive = str(tmp_path / "settings.zip")

    written = _backup.backup(archive)
    assert "lexicon.json" in written and "voice_settings.json" in written

    _backup.reset()
    assert _lexicon.load() == (0, {})
    assert _voicesettings.load() == ({}, [])

    restored = _backup.restore(archive)
    assert set(restored) == set(written)
    assert _lexicon.load()[1] == {"nvda": "ɛnviːdiːˈeɪ"}
    assert _voicesettings.load() == ({"v": {"rate": 80}}, ["v"])


def test_restoring_something_that_is_not_a_backup_is_refused(tmp_path):
    import zipfile
    from synthDrivers.piper import _backup
    other = tmp_path / "holiday-photos.zip"
    with zipfile.ZipFile(other, "w") as archive:
        archive.writestr("beach.jpg", b"not settings")
    with pytest.raises(_backup.BackupError):
        _backup.restore(str(other))


def test_backup_never_carries_voices_or_cache():
    """Voices download again and prepared audio rebuilds; only the settings
    files are work a user cannot recreate."""
    from synthDrivers.piper import _backup
    assert all(name.endswith(".json") for name in _backup.FILES)
    assert not any(name.endswith((".onnx", ".kcache")) for name in _backup.FILES)
    assert os.path.basename(_paths.cache_file()) not in _backup.FILES


def test_reset_keeps_downloaded_voices(tmp_path):
    from synthDrivers.piper import _backup, _lexicon
    _make_voice(_paths.voices_dir(), "en_US-lessac-medium")
    _lexicon.save({"a": "b"})
    _backup.reset()
    assert _lexicon.load() == (0, {})
    assert _paths.voice_installed("en_US-lessac-medium")
