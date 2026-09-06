"""Import voices that are already on disk.

Two sources are supported:

* Other Piper-based NVDA add-ons. Sonata Neural Voices and its maintained
  fork Dengjen keep voices in `<nvda config>/<addon>/voices/piper/<key>/`,
  one directory per voice holding a `.onnx` and a matching `.onnx.json`.
  Users switching over should not have to re-download gigabytes of models.
* A local file: either a voice archive (`.tar.gz`, the format those add-ons
  distribute) or a `.onnx` model with its `.onnx.json` beside it. This is the
  offline install path for machines with no internet access.

Nothing here touches NVDA or wx, so it is unit tested directly.
"""

import os
import shutil
import tarfile

from . import _paths

#: Data directories other Piper add-ons install voices into, relative to the
#: NVDA user config directory.
FOREIGN_VOICE_DIRS = (
    ("Sonata Neural Voices", os.path.join("sonata", "voices", "piper")),
    ("Dengjen Neural Voices", os.path.join("dengjen", "voices", "piper")),
)

MODEL_SUFFIX = ".onnx"
CONFIG_SUFFIX = ".onnx.json"


class ImportableVoice:
    """A voice found on disk that can be copied into our voices directory."""

    __slots__ = ("key", "source", "model_path", "config_path")

    def __init__(self, key, source, model_path, config_path):
        self.key = key
        self.source = source
        self.model_path = model_path
        self.config_path = config_path

    @property
    def installed(self):
        return _paths.voice_installed(self.key)

    @property
    def size(self):
        try:
            return os.path.getsize(self.model_path)
        except OSError:
            return 0


def _config_beside(model_path):
    """The `.onnx.json` for a model, or None when it is missing."""
    candidate = model_path + ".json"
    return candidate if os.path.isfile(candidate) else None


def _voice_key(model_path, fallback_dir=None):
    """Voice key for a model file.

    Other add-ons name the containing directory after the voice key
    (`en_US-lessac-medium`) but the model inside is often just
    `en_US-lessac-medium.onnx` or `model.onnx`, so prefer the directory when
    it carries the more specific name.
    """
    base = os.path.basename(model_path)[:-len(MODEL_SUFFIX)]
    if fallback_dir:
        folder = os.path.basename(fallback_dir.rstrip("\\/"))
        if folder and (base in ("model", "voice", "") or len(folder) > len(base)):
            return folder
    return base


def _scan_dir(root, source, found):
    for base, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(MODEL_SUFFIX):
                continue
            model = os.path.join(base, name)
            config = _config_beside(model)
            if config is None:
                continue
            key = _voice_key(model, base)
            if key not in found:
                found[key] = ImportableVoice(key, source, model, config)


def discover(config_path=None):
    """Find voices belonging to other Piper add-ons.

    `config_path` defaults to the NVDA user config directory; tests pass their
    own. Returns a list sorted by key, including voices we already have (the
    caller shows them as installed rather than hiding them).
    """
    if config_path is None:
        config_path = os.path.dirname(_paths.data_dir())
    found = {}
    for source, rel in FOREIGN_VOICE_DIRS:
        root = os.path.join(config_path, rel)
        if os.path.isdir(root):
            _scan_dir(root, source, found)
    return [found[k] for k in sorted(found)]


def import_voice(voice):
    """Copy one discovered voice into our voices directory. Returns its key."""
    dest_model = _paths.voice_model_path(voice.key)
    dest_config = _paths.voice_config_path(voice.key)
    os.makedirs(os.path.dirname(dest_model), exist_ok=True)
    shutil.copyfile(voice.model_path, dest_model + ".part")
    shutil.copyfile(voice.config_path, dest_config)
    os.replace(dest_model + ".part", dest_model)
    return voice.key


def import_voices(voices, progress=None):
    """Import several voices, skipping ones already installed.

    `progress` is called as progress(done_count, total_count). Returns the
    list of keys actually imported.
    """
    pending = [v for v in voices if not v.installed]
    done = []
    for i, voice in enumerate(pending):
        import_voice(voice)
        done.append(voice.key)
        if progress is not None:
            progress(i + 1, len(pending))
    return done


class VoiceImportError(Exception):
    """Raised when a file cannot be installed as a voice."""


def _safe_members(archive):
    """Yield only the model/config members, rejecting absolute paths, parent
    traversal, links, and devices, so a hostile archive cannot escape the
    destination directory."""
    for member in archive.getmembers():
        if not member.isfile():
            continue
        name = member.name.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            continue
        base = os.path.basename(name)
        if base.endswith(MODEL_SUFFIX) or base.endswith(CONFIG_SUFFIX):
            yield member, base


def install_from_archive(archive_path):
    """Install voices from a `.tar.gz` voice archive. Returns the keys added."""
    voices_dir = _paths.voices_dir()
    os.makedirs(voices_dir, exist_ok=True)
    models = {}
    configs = {}
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            for member, base in _safe_members(archive):
                src = archive.extractfile(member)
                if src is None:
                    continue
                target = os.path.join(voices_dir, base + ".part")
                with src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                if base.endswith(CONFIG_SUFFIX):
                    configs[base[:-len(CONFIG_SUFFIX)]] = target
                else:
                    models[base[:-len(MODEL_SUFFIX)]] = target
    except (tarfile.TarError, OSError) as e:
        _discard(models, configs)
        raise VoiceImportError(str(e))

    keys = sorted(set(models) & set(configs))
    if not keys:
        _discard(models, configs)
        raise VoiceImportError("no voice model and configuration pair found")
    for key in keys:
        os.replace(configs.pop(key), _paths.voice_config_path(key))
        os.replace(models.pop(key), _paths.voice_model_path(key))
    _discard(models, configs)
    return keys


def install_from_model(model_path):
    """Install a `.onnx` model that has its `.onnx.json` beside it."""
    config_path = _config_beside(model_path)
    if config_path is None:
        raise VoiceImportError(
            "%s is missing next to the model"
            % os.path.basename(model_path + ".json"))
    key = _voice_key(model_path)
    voice = ImportableVoice(key, "file", model_path, config_path)
    import_voice(voice)
    return [key]


def install_from_file(path_):
    """Install from either a voice archive or a model file. Returns keys."""
    lower = path_.lower()
    if lower.endswith(MODEL_SUFFIX):
        return install_from_model(path_)
    if lower.endswith((".tar.gz", ".tgz", ".tar")):
        return install_from_archive(path_)
    raise VoiceImportError("unsupported file type")


def _discard(*groups):
    for group in groups:
        for temp in group.values():
            try:
                os.remove(temp)
            except OSError:
                pass
