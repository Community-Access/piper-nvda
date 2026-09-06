"""Tests for the Piper voice catalog parser and the download engine."""

import io
import json
import os

import pytest

from synthDrivers.piper import _catalog, _download


SAMPLE_CATALOG = {
    "en_US-lessac-medium": {
        "key": "en_US-lessac-medium",
        "name": "lessac",
        "language": {"code": "en_US", "family": "en", "region": "US",
                     "name_native": "English", "name_english": "English",
                     "country_english": "United States"},
        "quality": "medium",
        "num_speakers": 1,
        "speaker_id_map": {},
        "files": {
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx":
                {"size_bytes": 63201294, "md5_digest": "abc"},
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json":
                {"size_bytes": 4885, "md5_digest": "def"},
            "en/en_US/lessac/medium/MODEL_CARD":
                {"size_bytes": 284, "md5_digest": "ghi"},
        },
        "aliases": [],
    },
    "bn_BD-google-medium": {
        "key": "bn_BD-google-medium",
        "name": "google",
        "language": {"code": "bn_BD", "family": "bn", "region": "BD",
                     "name_native": "বাংলা", "name_english": "Bengali",
                     "country_english": "Bangladesh"},
        "quality": "medium",
        "num_speakers": 16,
        "speaker_id_map": {"00737": 0, "01232": 1},
        "files": {
            "bn/bn_BD/google/medium/bn_BD-google-medium.onnx":
                {"size_bytes": 100, "md5_digest": "m"},
            "bn/bn_BD/google/medium/bn_BD-google-medium.onnx.json":
                {"size_bytes": 10, "md5_digest": "c"},
        },
    },
}


def test_voice_parsing_and_urls():
    v = _catalog.Voice("en_US-lessac-medium",
                       SAMPLE_CATALOG["en_US-lessac-medium"])
    assert v.lang_english == "English"
    assert v.quality == "medium"
    assert v.num_speakers == 1
    assert v.model_url.endswith("/en/en_US/lessac/medium/en_US-lessac-medium.onnx")
    assert v.config_url.endswith(".onnx.json")
    assert v.sample_url(0).endswith(
        "/en/en_US/lessac/medium/samples/speaker_0.mp3")
    assert v.model_md5 == "abc"
    assert "English" in v.display_name


def test_multispeaker_sample_and_display():
    v = _catalog.Voice("bn_BD-google-medium",
                       SAMPLE_CATALOG["bn_BD-google-medium"])
    assert v.num_speakers == 16
    assert "16 speakers" in v.display_name
    assert v.sample_url(3).endswith("samples/speaker_3.mp3")


def test_load_catalog_from_disk(tmp_path, monkeypatch):
    from synthDrivers.piper import _paths
    data = tmp_path / "piper"
    data.mkdir()
    (data / "voices.json").write_text(json.dumps(SAMPLE_CATALOG),
                                      encoding="utf-8")
    monkeypatch.setattr(_paths, "data_dir", lambda: str(data))
    voices = _catalog.load_catalog()
    assert len(voices) == 2
    keys = {v.key for v in voices}
    assert "en_US-lessac-medium" in keys


class _FakeResponse:
    def __init__(self, data, status=200, content_length=None):
        self._buf = io.BytesIO(data)
        self.status = status
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, n):
        return self._buf.read(n)


def test_download_url_md5_verified(tmp_path):
    import hashlib
    data = b"piper voice bytes" * 500
    md5 = hashlib.md5(data).hexdigest()
    dest = str(tmp_path / "v.onnx")
    _download.download_url("http://x/v.onnx", dest, md5, len(data),
                           opener=lambda r: _FakeResponse(data, 200, len(data)))
    assert open(dest, "rb").read() == data


def test_download_url_bad_md5_rejected(tmp_path):
    dest = str(tmp_path / "v.onnx")
    with pytest.raises(_download.DownloadError):
        _download.download_url("http://x", dest, "0" * 32, 4,
                               opener=lambda r: _FakeResponse(b"data", 200, 4))
    assert not os.path.isfile(dest)


def test_download_url_resumes(tmp_path):
    import hashlib
    data = b"0123456789" * 400
    md5 = hashlib.md5(data).hexdigest()
    dest = str(tmp_path / "v.onnx")
    with open(dest + ".part", "wb") as f:
        f.write(data[:1500])
    captured = {}

    def opener(request):
        rng = request.get_header("Range")
        captured["range"] = rng
        start = int(rng.split("=")[1].split("-")[0])
        return _FakeResponse(data[start:], status=206)

    _download.download_url("http://x", dest, md5, len(data), opener=opener)
    assert captured["range"] == "bytes=1500-"
    assert open(dest, "rb").read() == data
