"""Resumable, md5-verified downloader for Piper voices.

The engine (`download_url`) has no NVDA/wx dependency and is unit tested. The
wx UI lives in _download_ui.py.
"""

import hashlib
import os
import urllib.request

from . import _catalog, _paths


class DownloadError(Exception):
    pass


class Cancelled(Exception):
    pass


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_url(url, dest, expected_md5=None, expected_size=0,
                 progress=None, should_cancel=None, opener=None):
    """Download `url` to `dest`, resuming a `.part` file when the server
    supports ranged requests, and verifying md5 (if given) before rename."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.isfile(part) else 0

    request = urllib.request.Request(url)
    if have:
        request.add_header("Range", "bytes=%d-" % have)
    open_fn = opener or urllib.request.urlopen
    try:
        response = open_fn(request)
    except Exception as e:
        raise DownloadError("could not open %s: %s" % (url, e))

    status = getattr(response, "status", None)
    append = have > 0 and status == 206
    if not append:
        have = 0
    total = expected_size
    if hasattr(response, "headers"):
        cl = response.headers.get("Content-Length")
        if cl and not append:
            try:
                total = int(cl)
            except ValueError:
                pass

    mode = "ab" if append else "wb"
    with open(part, mode) as f:
        while True:
            if should_cancel is not None and should_cancel():
                raise Cancelled()
            chunk = response.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            have += len(chunk)
            if progress is not None:
                progress(have, total)

    if expected_md5:
        actual = _md5(part)
        if actual != expected_md5:
            os.remove(part)
            raise DownloadError("checksum mismatch for %s"
                                % os.path.basename(dest))
    os.replace(part, dest)


def download_voice(voice, progress=None, should_cancel=None, opener=None):
    """Download a Voice's model and config into the voices dir. `progress` is
    called as progress(done_bytes, total_bytes)."""
    model_dest = _paths.voice_model_path(voice.key)
    config_dest = _paths.voice_config_path(voice.key)
    total = voice.model_size or 0

    def model_progress(done, _t):
        if progress is not None:
            progress(done, total)

    download_url(voice.model_url, model_dest, voice.model_md5,
                 voice.model_size, progress=model_progress,
                 should_cancel=should_cancel, opener=opener)
    download_url(voice.config_url, config_dest, voice.config_md5,
                 progress=None, should_cancel=should_cancel, opener=opener)


def remove_voice(voice_key):
    for path in (_paths.voice_model_path(voice_key),
                 _paths.voice_config_path(voice_key)):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
