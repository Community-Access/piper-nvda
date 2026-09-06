"""Piper voice catalog from the rhasspy/piper-voices HuggingFace repo.

Parses voices.json into a list of Voice records and builds the download URLs
for each voice's model, config, and demo sample.
"""

import hashlib
import json
import os
import urllib.parse
import urllib.request

from . import _paths

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
CATALOG_URL = HF_BASE + "voices.json"


def file_url(relative_path):
    """Absolute download URL for a path from the catalog.

    Catalog paths carry the voice's own name, which is not always ASCII
    (`pt_PT-tug\u00e3o-medium`). `urllib` refuses to send a non-ASCII URL, so
    percent-encode the path while leaving the separators alone.
    """
    return HF_BASE + urllib.parse.quote(relative_path, safe="/")


class Voice:
    __slots__ = ("key", "name", "language", "lang_code", "lang_native",
                 "lang_english", "region", "quality", "num_speakers",
                 "speaker_id_map", "model_rel", "config_rel", "model_md5",
                 "config_md5", "model_size")

    def __init__(self, key, entry):
        self.key = key
        self.name = entry.get("name", key)
        lang = entry.get("language", {})
        self.lang_code = lang.get("code", "")
        self.lang_native = lang.get("name_native", "")
        self.lang_english = lang.get("name_english", self.lang_code)
        self.region = lang.get("country_english", "")
        self.quality = entry.get("quality", "")
        self.num_speakers = entry.get("num_speakers", 1)
        self.speaker_id_map = entry.get("speaker_id_map") or {}
        self.model_rel = None
        self.config_rel = None
        self.model_md5 = None
        self.config_md5 = None
        self.model_size = 0
        for path, meta in (entry.get("files") or {}).items():
            if path.endswith(".onnx"):
                self.model_rel = path
                self.model_md5 = meta.get("md5_digest")
                self.model_size = meta.get("size_bytes", 0)
            elif path.endswith(".onnx.json"):
                self.config_rel = path
                self.config_md5 = meta.get("md5_digest")

    @property
    def display_name(self):
        speakers = (" - %d speakers" % self.num_speakers
                    if self.num_speakers > 1 else "")
        return "%s (%s, %s%s)" % (
            self.name.title(), self.lang_english, self.quality, speakers)

    @property
    def model_url(self):
        return file_url(self.model_rel)

    @property
    def config_url(self):
        return file_url(self.config_rel)

    def sample_url(self, speaker=0):
        # samples live next to the model: <dir>/samples/speaker_<n>.mp3
        model_dir = self.model_rel.rsplit("/", 1)[0]
        return file_url("%s/samples/speaker_%d.mp3" % (model_dir, speaker))

    @property
    def installed(self):
        return _paths.voice_installed(self.key)


#: Quality order for a recommendation. Medium is the balance most people
#: want; low and x_low are faster on a modest machine; high is the slowest.
QUALITY_PREFERENCE = ("medium", "low", "high", "x_low")


def recommend(voices, language):
    """The voice to offer someone who has none yet, for their language.

    Prefers a voice for the exact language tag, then one for the primary
    subtag, so a user running `en_GB` is offered a British voice if there is
    one and an English voice otherwise. Within that, medium quality first and
    then the smallest download, which keeps the first run short. Returns None
    when nothing matches, and the caller falls back to the full browser.
    """
    wanted = (language or "").replace("-", "_").lower()
    if not wanted:
        return None
    base = wanted.split("_", 1)[0]

    def rank(voice):
        quality = voice.quality or ""
        try:
            quality_rank = QUALITY_PREFERENCE.index(quality)
        except ValueError:
            quality_rank = len(QUALITY_PREFERENCE)
        return (quality_rank, voice.model_size or 0, voice.key)

    for match in (wanted, base):
        candidates = [
            v for v in voices
            if (v.lang_code or "").lower().replace("-", "_") == match
            or (match == base
                and (v.lang_code or "").lower().split("_", 1)[0] == base)
        ]
        if candidates:
            return sorted(candidates, key=rank)[0]
    return None


def download_catalog(opener=None):
    """Fetch voices.json to the data dir if not already present. Returns the
    local path."""
    dest = _paths.catalog_path()
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open_fn = opener or urllib.request.urlopen
    resp = open_fn(CATALOG_URL)
    data = resp.read()
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return dest


def load_catalog():
    """Return a list of Voice records, or [] if the catalog is missing."""
    path = _paths.catalog_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    return [Voice(key, entry) for key, entry in raw.items()]


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
