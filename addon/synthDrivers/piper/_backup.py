"""Backing up and restoring the settings that are the user's own work.

Voices can be downloaded again and prepared audio can be rebuilt. What cannot
is the pronunciations someone has corrected one at a time, the voice they
picked for each language, the phrases they asked to have prepared, and the
settings they tuned per voice. That is what this saves, as a single file they
can keep somewhere safe or carry to another machine.

Deliberately not included: the voices themselves, which are large and
downloadable, and the prepared audio, which is derived.

No NVDA or wx dependency, so this is unit tested directly.
"""

import os
import zipfile

from . import _paths

#: The files that hold work a user cannot easily recreate.
FILES = (
    "lexicon.json",
    "language_voices.json",
    "warmup.json",
    "voice_settings.json",
)

#: Written into the archive so a restore can tell one of ours from any other
#: zip a user might pick by mistake.
MARKER = "piper-settings.txt"
MARKER_TEXT = "Piper Neural Voices for NVDA: settings backup\n"


class BackupError(Exception):
    """Raised when a backup cannot be written or read."""


def backup(dest_path):
    """Write the settings files that exist into a zip. Returns their names."""
    written = []
    try:
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MARKER, MARKER_TEXT)
            for name in FILES:
                source = os.path.join(_paths.data_dir(), name)
                if os.path.isfile(source):
                    archive.write(source, name)
                    written.append(name)
    except (OSError, zipfile.BadZipFile) as e:
        raise BackupError(str(e))
    return written


def inspect(archive_path):
    """The settings files an archive contains, or raise if it is not ours."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as e:
        raise BackupError(str(e))
    found = [name for name in FILES if name in names]
    if MARKER not in names or not found:
        raise BackupError("this is not a Piper settings backup")
    return found


def restore(archive_path):
    """Replace the settings files an archive holds. Returns their names.

    Only the known names are taken, and each is written to the data directory
    by name, so an archive cannot place a file anywhere else.
    """
    found = inspect(archive_path)
    data_dir = _paths.data_dir()
    os.makedirs(data_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for name in found:
                content = archive.read(name)
                target = os.path.join(data_dir, name)
                tmp = target + ".part"
                with open(tmp, "wb") as f:
                    f.write(content)
                os.replace(tmp, target)
    except (OSError, zipfile.BadZipFile) as e:
        raise BackupError(str(e))
    return found


def reset():
    """Delete every settings file, returning the ones that were there.

    Voices and prepared audio are left alone: this is for starting the
    configuration again, not for uninstalling.
    """
    removed = []
    for name in FILES:
        target = os.path.join(_paths.data_dir(), name)
        try:
            if os.path.isfile(target):
                os.remove(target)
                removed.append(name)
        except OSError:
            pass
    return removed
