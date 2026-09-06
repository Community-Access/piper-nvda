"""Installed-voice catalog for the driver: cross-references installed voice
files with the downloaded voices.json for language/speaker metadata, falling
back to each voice's local .onnx.json when the catalog is absent.
"""

import json

from . import _catalog, _paths


class InstalledVoice:
    __slots__ = ("key", "display_name", "language", "espeak_lang",
                 "num_speakers", "speaker_id_map")

    def __init__(self, key, display_name, language, espeak_lang,
                 num_speakers, speaker_id_map):
        self.key = key
        self.display_name = display_name
        self.language = language
        self.espeak_lang = espeak_lang
        self.num_speakers = num_speakers
        self.speaker_id_map = speaker_id_map


def _from_local_config(key):
    """Read language and speakers from a voice's local .onnx.json."""
    try:
        with open(_paths.voice_config_path(key), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    lang = cfg.get("language", {})
    code = lang.get("code", "")
    return InstalledVoice(
        key=key,
        display_name=key,
        language=code.replace("-", "_") if code else key,
        espeak_lang=cfg.get("espeak", {}).get("voice", "en-us"),
        num_speakers=cfg.get("num_speakers", 1),
        speaker_id_map=cfg.get("speaker_id_map") or {},
    )


def load_installed():
    """Return a list of InstalledVoice, sorted by language then name."""
    catalog = {v.key: v for v in _catalog.load_catalog()}
    voices = []
    for key in _paths.installed_voice_keys():
        cat = catalog.get(key)
        local = _from_local_config(key)
        if cat is not None:
            voices.append(InstalledVoice(
                key=key,
                display_name=cat.display_name,
                language=(cat.lang_code or "").replace("-", "_"),
                espeak_lang=local.espeak_lang if local else "en-us",
                num_speakers=cat.num_speakers,
                speaker_id_map=cat.speaker_id_map,
            ))
        elif local is not None:
            local.display_name = key
            voices.append(local)
    voices.sort(key=lambda v: (v.language, v.display_name))
    return voices


def default_voice_for_language(voices, language):
    if not voices:
        return None
    lang = (language or "").replace("-", "_").lower()
    base = lang.split("_", 1)[0]
    for v in voices:
        if v.language.lower() == lang:
            return v.key
    for v in voices:
        if v.language.lower().split("_", 1)[0] == base:
            return v.key
    return None
